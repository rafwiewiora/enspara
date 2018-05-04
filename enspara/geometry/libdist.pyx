import numpy as np
from cython.parallel import prange

from enspara import exception

cimport cython
cimport numpy as np

ctypedef fused FLOAT_TYPE_T:
    np.int8_t
    np.int16_t
    np.int32_t
    np.int64_t
    np.float32_t
    np.float64_t

cdef extern from "math.h" nogil:
    double sqrt(double x)

@cython.boundscheck(False)
@cython.wraparound(False)
def _euclidean(np.ndarray[FLOAT_TYPE_T, ndim=2] X,
               np.ndarray[FLOAT_TYPE_T, ndim=1] y,
               np.ndarray[np.float64_t, ndim=1] out):
    
    cdef long n_samples = len(out)
    cdef long n_features = len(y)
    assert len(out) == X.shape[0]
    assert n_features == X.shape[1]

    cdef long i, j = 0
    for i in prange(n_samples, nogil=True):
        out[i] = 0

    for i in prange(n_samples, nogil=True):
        for j in range(n_features):
            out[i] += (X[i, j] - y[j])**2

    for i in prange(n_samples, nogil=True):
        out[i] = sqrt(out[i])

    return out.reshape(-1, 1)

def euclidean(X, y, out=None):
    """Compute the euclidean distance between a point, `y`, and a group
    of points `X`. Uses thread-parallelism with OpenMP.

    Parameters
    ----------
    X : array, shape=(n_samples, n_features)
        The group of points for which to compute the distance from `y`.
    y: array, shape=(n_features)
        The point, for all rows in `X`, to compute the distance to.
    out: array, shape=(n_samples), default=None
        If provided, the array to place the distances in. If not provided,
        an array will be allocated for you.
    """

    if len(X.shape) != 2:
        raise exception.DataInvalid(
            "Data array dimension must be two, got shape %s." %
            str(X.shape))
    if len(y.shape) != 1:
        raise exception.DataInvalid(
            "Target point dimension must be one, got shape %s." %
            str(X.shape))
    if X.shape[1] != y.shape[0]:
        raise exception.DataInvalid(
            ("Target data point dimension (%s) must match data " +
             "array dimension (%s)") % (y.shape[0], X.shape[1]))

    # if `out` isn't provided, allocate it.
    # if `out` is provided, check it for appropriateness
    if out is None:
        out = np.zeros((X.shape[0]), dtype=np.float64)
    else:
        # precision problems happen if out is less than 64-bit
        if out.dtype != np.float64:
            raise exception.DataInvalid(
                "In-place output array must be np.float64, got '%s'."
                % out.dtype)
        if out.shape[0] != X.shape[0]:
            raise exception.DataInvalid(
                ("In-place output array dimension (%s) must match number of "
                 "samples in data array (%s)") % (out.shape[0], X.shape[0]))
        if len(out.shape) != 1:
            raise exception.DataInvalid(
                "In-place output array must be one-dimensional, "
                "got shape %s" %
                out.shape)

    _euclidean(X, y, out)
    return out
