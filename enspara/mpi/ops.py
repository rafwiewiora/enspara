import logging
import numpy as np

from sklearn.utils import check_random_state

from ..exception import ImproperlyConfigured, DataInvalid
from ..util import array as ra

from . import MPI, MPI_RANK, MPI_SIZE

COMM = MPI.COMM_WORLD
logger = logging.getLogger(__name__)


def convert_local_indices(local_ctr_inds, global_lengths):
    """Convert indices from (rank, local_frame) to (global frame).

    In enspara's clustering code, we represent frames in the data set by
    the pairs (owner_rank, local_frame), rather than (global_frame).
    This routine converts the local indices to global indices given the
    global lengths.

    Parameters
    ----------
    local_indices : iterable of tuples
        A list of tuples of the form `(owner_rank, local_frame)`.
    global_lengths : np.ndarray
        Array of the length of each trajectory distributed across all
        the nodes.
    """

    global_indexing = np.arange(np.sum(global_lengths))
    file_origin_ra = ra.RaggedArray(global_indexing, lengths=global_lengths)

    ctr_inds = []
    for rank, local_fid in local_ctr_inds:
        global_fid = file_origin_ra[rank::MPI_SIZE].flatten()[local_fid]
        ctr_inds.append(global_fid)

    return ctr_inds


def assemble_striped_array(local_arr):
    """Assemble an striped array.

    By 'striped array', we mean an array that has element i on node
    i % n. This is a common strategy for spreading data across MPI
    nodes, because it is easy to compute and, in practice, often spreads
    data pretty evenly.

    Parameters
    ----------
    local_array: np.ndarray
        The array to spread across nodes.

    Returns
    -------
    global_array: np.ndarray
        Full array that is striped across all nodes.
    """

    total_dim1 = COMM.allreduce(len(local_arr), op=MPI.SUM)
    total_shape = (total_dim1,) + local_arr.shape[1:]

    if not np.all(local_arr > 0):
        raise ImproperlyConfigured("On rank %s, a length <= 0 was found. Lengths must be strictly greater than zero." % MPI_RANK)

    global_lengths = np.zeros(total_shape, dtype=local_arr.dtype) - 1

    for i in range(MPI_SIZE):
        global_lengths[i::MPI_SIZE] = COMM.bcast(local_arr, root=i)

    assert np.all(global_lengths > 0), global_lengths

    return global_lengths


def assemble_striped_ragged_array(local_array, global_lengths):
    """Assemble an array that is striped according to the first dim of a
    ragged array.

    This is relevant because, unlike a regular striped array, the
    striping is complex, since the length of each row of the RA can be
    different.

    This is used e.g. to assemble assignments in clustering from data
    spread across each node.

    Parameters
    ----------
    local_array: np.ndarray
        The array to spread across nodes.
    global_lengths: np.ndarray
        Lengths for each row of the RA. The ultimate assembled RA will
        have this as it's lengths attribute.

    Returns
    -------
    global_ra: np.ndarray
        Full array that is striped across all nodes.
    """

    assert np.issubdtype(type(global_lengths[0]), np.integer)

    global_array = np.zeros(shape=(np.sum(global_lengths),)) - 1
    global_ra = ra.RaggedArray(global_array, lengths=global_lengths)

    for rank in range(MPI_SIZE):
        rank_array = COMM.bcast(local_array, root=rank)

        local_lengths = global_lengths[rank::MPI_SIZE]
        if len(local_lengths) > 1:
            rank_ra = ra.RaggedArray(
                rank_array, lengths=local_lengths)
            global_ra[rank::MPI_SIZE] = rank_ra
        else:
            global_ra[rank] = rank_array

    assert np.all(global_ra._data) >= 0

    return global_ra._data.astype(local_array.dtype)


def mean(local_array):
    """Compute the mean of an array across all MPI nodes.
    """

    local_sum = np.sum(local_array)
    local_len = len(local_array)

    global_sum = np.zeros(1) - 1
    global_len = np.zeros(1) - 1

    global_sum = COMM.allreduce(local_sum, op=MPI.SUM)
    global_len = COMM.allreduce(local_len, op=MPI.SUM)

    assert global_len >= 0
    assert global_sum >= local_sum

    return global_sum / global_len


def distribute_frame(data, world_index, owner_rank):
    """Distribute an element of an array to every node in an MPI swarm.

    Parameters
    ----------
    data : array-like or md.Trajectory
        Data array with frames to distribute. The frame will be taken
        from axis 0 of the input.
    world_index : int
        Position of the target frame in `data` on the node that owns it
    owner_rank : int
        Rank of the node that owns the datum that we'll broadcast.
    out : array-like or md.Trajectory
        An array or trajectory to place the new data into.

    Returns
    -------
    frame : array-like or md.Trajectory
        A single slice of `data`, of shape `data.shape[1:]`.
    """

    if owner_rank >= MPI_SIZE:
        raise ImproperlyConfigured(
            'In MPI swarm of size %s, recieved owner rank == %s.',
            MPI_SIZE, owner_rank)

    if hasattr(data, 'xyz'):
        if MPI_RANK == owner_rank:
            frame = data[world_index].xyz
        else:
            frame = np.empty_like(data[0].xyz)
    else:
        if MPI_RANK == owner_rank:
            frame = data[world_index]
        else:
            frame = np.empty_like(data[0])

    MPI.COMM_WORLD.Bcast(frame, root=owner_rank)

    if hasattr(data, 'xyz'):
        wrapped_data = type(data)(xyz=frame, topology=data.top)
        return wrapped_data
    else:
        return frame


def randind(local_array, random_state=None):
    """Given the local fragment of an assumed-larger array, give the
    location of a randomly chosen element of the array (uniformly
    distributed).

    Parameters
    ----------
    local_array : ndarray
        An array that's striped across multiple nodes in an MPI swarm.
    random_state : int or np.RandomState
        State of the RNG to use for the randomized part of the choice.

    Returns
    -------
    owner_rank : int
        Rank of the node that owns the element that's chosen.
    local_index : int
        Index within the owner node's local array.
    """

    random_state = check_random_state(random_state)

    # First thing, we need to find out how long all the local arrays are.
    n_states = np.array(COMM.allgather(len(local_array)))
    assert np.all(n_states >= 0)

    if sum(n_states) < 1:
        raise DataInvalid(
            "Random choice requires a non-empty array. Got shapes: %s" %
            n_states)

    # Then, we select a random index from amongst the total lengths
    if MPI_RANK == 0:
        # this is modeled after numpy.random.choice, but for some reason
        # our formulation here gives the samer results.
        global_index = random_state.randint(sum(n_states))
    else:
        global_index = None

    global_index = MPI.COMM_WORLD.bcast(global_index, root=0)

    # this computation is the same as finding global_index % MPI_SIZE and
    # global_index // MPI_SIZE iff our data are 'packed' on nodes, but not
    # otherwise.

    concat = np.concatenate([np.arange(sum(n_states))[r::MPI_SIZE]
                             for r in range(MPI_SIZE)])
    a = ra.RaggedArray(
        concat,
        lengths=n_states,
        error_checking=False)

    owner_rank, local_index = ra.where(a == global_index)
    owner_rank, local_index = owner_rank[0], local_index[0]

    assert local_index >= 0

    return (owner_rank, local_index)
