from numpy.core.numeric import errstate, less_equal, isscalar, array, multiarray, isfinite, zeros_like, ones_like, isnan, any, all

def isclose(a, b, rtol=1.e-5, atol=1.e-8, equal_nan=False):
    """
    Returns a boolean array where two arrays are element-wise equal within a
    tolerance.

    The tolerance values are positive, typically very small numbers.  The
    relative difference (`rtol` * abs(`b`)) and the absolute difference
    `atol` are added together to compare against the absolute difference
    between `a` and `b`.

    Parameters
    ----------
    a, b : array_like
        Input arrays to compare.
    rtol : float
        The relative tolerance parameter (see Notes).
    atol : float
        The absolute tolerance parameter (see Notes).
    equal_nan : bool
        Whether to compare NaN's as equal.  If True, NaN's in `a` will be
        considered equal to NaN's in `b` in the output array.

    Returns
    -------
    y : array_like
        Returns a boolean array of where `a` and `b` are equal within the
        given tolerance. If both `a` and `b` are scalars, returns a single
        boolean value.

    See Also
    --------
    allclose

    Notes
    -----
    .. versionadded:: 1.7.0

    For finite values, isclose uses the following equation to test whether
    two floating point values are equivalent.

     absolute(`a` - `b`) <= (`atol` + `rtol` * absolute(`b`))

    The above equation is not symmetric in `a` and `b`, so that
    `isclose(a, b)` might be different from `isclose(b, a)` in
    some rare cases.

    Examples
    --------
    >>> np.isclose([1e10,1e-7], [1.00001e10,1e-8])
    array([True, False])
    >>> np.isclose([1e10,1e-8], [1.00001e10,1e-9])
    array([True, True])
    >>> np.isclose([1e10,1e-8], [1.0001e10,1e-9])
    array([False, True])
    >>> np.isclose([1.0, np.nan], [1.0, np.nan])
    array([True, False])
    >>> np.isclose([1.0, np.nan], [1.0, np.nan], equal_nan=True)
    array([True, True])
    """
    def within_tol(x, y, atol, rtol):
        with errstate(invalid='ignore'):
            result = less_equal(abs(x-y), atol + rtol * abs(y))
        if isscalar(a) and isscalar(b):
            result = bool(result)
        return result

    x = array(a, copy=False, subok=True, ndmin=1)
    y = array(b, copy=False, subok=True, ndmin=1)

    # Make sure y is an inexact type to avoid bad behavior on abs(MIN_INT).
    # This will cause casting of x later. Also, make sure to allow subclasses
    # (e.g., for numpy.ma).
    dt = multiarray.result_type(y, 1.)
    y = array(y, dtype=dt, copy=False, subok=True)

    xfin = isfinite(x)
    yfin = isfinite(y)
    if all(xfin) and all(yfin):
        return within_tol(x, y, atol, rtol)
    else:
        finite = xfin & yfin
        cond = zeros_like(finite, subok=True)
        # Because we're using boolean indexing, x & y must be the same shape.
        # Ideally, we'd just do x, y = broadcast_arrays(x, y). It's in
        # lib.stride_tricks, though, so we can't import it here.
        x = x * ones_like(cond)
        y = y * ones_like(cond)
        # Avoid subtraction with infinite/nan values...
        cond[finite] = within_tol(x[finite], y[finite], atol, rtol)
        # Check for equality of infinite values...
        cond[~finite] = (x[~finite] == y[~finite])
        if equal_nan:
            # Make NaN == NaN
            both_nan = isnan(x) & isnan(y)
            cond[both_nan] = both_nan[both_nan]

        if isscalar(a) and isscalar(b):
            return bool(cond)
        else:
            return cond
