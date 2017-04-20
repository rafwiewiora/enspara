import numpy as np
import mdtraj as md

from nose.tools import assert_equal, assert_is, assert_is_not
from mdtraj.testing import get_fn
from numpy.testing import assert_array_equal

from enspara.cluster.util import find_cluster_centers, ClusterResult
from enspara.util import array as ra

from . import save_states


def test_ClusterResult_partition_np():
    list_lens = [20, 20, 20]

    concat_assigs = [0]*20 + [1]*20 + [2]*20
    concat_dists = [0.2]*20 + [0.3]*20 + [0.4]*20
    concat_ctr_inds = [3, 23, 43]

    concat_rslt = ClusterResult(
        assignments=concat_assigs,
        distances=concat_dists,
        center_indices=concat_ctr_inds,
        centers=None)

    rslt = concat_rslt.partition(list_lens)

    # ensuring it isn't a ragged array allows list, ndarray or maskedarray
    assert_is_not(type(rslt.assignments), ra.RaggedArray)
    assert_array_equal(rslt.assignments[0], [0]*20)
    assert_array_equal(rslt.assignments[1], [1]*20)
    assert_array_equal(rslt.assignments[2], [2]*20)

    assert_is_not(type(rslt.distances), ra.RaggedArray)
    assert_array_equal(rslt.distances[0], [0.2]*20)
    assert_array_equal(rslt.distances[1], [0.3]*20)
    assert_array_equal(rslt.distances[2], [0.4]*20)

    assert_array_equal(rslt.center_indices, [(0, 3), (1, 3), (2, 3)])

    # force raggedness
    rslt = concat_rslt.partition(list_lens, square=False)

    assert_is(type(rslt.assignments), ra.RaggedArray)
    assert_array_equal(rslt.assignments[0], [0]*20)
    assert_array_equal(rslt.assignments[1], [1]*20)
    assert_array_equal(rslt.assignments[2], [2]*20)

    assert_is(type(rslt.distances), ra.RaggedArray)
    assert_array_equal(rslt.distances[0], [0.2]*20)
    assert_array_equal(rslt.distances[1], [0.3]*20)
    assert_array_equal(rslt.distances[2], [0.4]*20)

    assert_array_equal(rslt.center_indices, [(0, 3), (1, 3), (2, 3)])


def test_ClusterResult_partition_ra():
    list_lens = [10, 20, 100]

    concat_assigs = [0]*10 + [1]*20 + [2]*100
    concat_dists = [0.2]*10 + [0.3]*20 + [0.4]*100
    concat_ctr_inds = [3, 23, 103]

    concat_rslt = ClusterResult(
        assignments=concat_assigs,
        distances=concat_dists,
        center_indices=concat_ctr_inds,
        centers=None)

    rslt = concat_rslt.partition(list_lens)

    assert_is(type(rslt.assignments), ra.RaggedArray)
    assert_array_equal(rslt.assignments[0], [0]*10)
    assert_array_equal(rslt.assignments[1], [1]*20)
    assert_array_equal(rslt.assignments[2], [2]*100)

    assert_is(type(rslt.distances), ra.RaggedArray)
    assert_array_equal(rslt.distances[0], [0.2]*10)
    assert_array_equal(rslt.distances[1], [0.3]*20)
    assert_array_equal(rslt.distances[2], [0.4]*100)

    assert_array_equal(rslt.center_indices, [(0, 3), (1, 13), (2, 73)])

    # force squareness
    rslt = concat_rslt.partition(list_lens, square=True)

    assert_is_not(type(rslt.assignments), ra.RaggedArray)
    assert_equal(rslt.assignments.shape, (3, 100))
    assert_array_equal(rslt.assignments[0, 0:10], [0]*10)
    assert_array_equal(rslt.assignments[1, 0:20], [1]*20)
    assert_array_equal(rslt.assignments[2], [2]*100)

    assert_is_not(type(rslt.distances), ra.RaggedArray)
    assert_equal(rslt.distances.shape, (3, 100))
    assert_array_equal(rslt.distances[0, 0:10], [0.2]*10)
    assert_array_equal(rslt.distances[1, 0:20], [0.3]*20)
    assert_array_equal(rslt.distances[2], [0.4]*100)

    assert_array_equal(rslt.center_indices, [(0, 3), (1, 13), (2, 73)])


def test_unique_state_extraction():
    '''
    Check to makes sure we get the unique states from the trajectory
    correctly
    '''

    states = [0, 1, 2, 3, 4]
    assignments = np.random.choice(states, (100000))

    assert all(save_states.unique_states(assignments) == states)

    states = [-1, 0, 1, 2, 3, 4]
    assignments = np.random.choice(states, (100000))

    assert all(save_states.unique_states(assignments) == states[1:])


def test_find_cluster_centers():

    N_TRJS = 20
    many_trjs = [md.load(get_fn('frame0.xtc'), top=get_fn('native.pdb'))
                 for i in range(N_TRJS)]

    distances = np.ones((N_TRJS, len(many_trjs[0])))

    center_inds = [(0, 0), (5, 2), (15, 300)]

    for ind in center_inds:
        distances[center_inds[0], center_inds[1]] = 0

    centers = find_cluster_centers(many_trjs, distances)

    # we should get back the same number of centers as there are zeroes
    # in the distances matrix
    assert_equal(len(centers), np.count_nonzero(distances == 0))

    for indx in center_inds:
        expected_xyz = many_trjs[indx[0]][indx[1]].xyz
        assert np.any(expected_xyz == np.array([c.xyz for c in centers]))
