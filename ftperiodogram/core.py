"""
Core algorithm for the Fast Template Periodogram

(c) John Hoffman, Jake Vanderplas 2017
"""
from __future__ import print_function


import numpy as np

from .summations import fast_summations, direct_summations

from .pseudo_poly import compute_polynomial_tensors,\
                         get_polynomial_vectors,\
                         compute_zeros, compute_zeros_multifrequency

from .utils import Avec, Bvec, ModelFitParams, weights



def fit_template(t, y, dy, cn, sn, ptensors, freq, sums=None,
                       allow_negative_amplitudes=True, zeros=None,
                       small=1E-7):
    r"""
    Fits periodic template to data at a single frequency

    Parameters
    ----------
    t : array_like
        Measurement times (must be monotonically increasing)
    y : array_like
        Measurement values at corresponding measurement times
    dy : array_like
        Measurement uncertainties
    cn : array_like
        Fourier (cosine) coefficients of the template
    sn : array_like
        Fourier (sine) coefficients of the template
    ptensors : np.ndarray, shape = (H, H, H, L)
        Polynomial coefficients from template; H is the number of
        harmonics, L is the (maximum) length of the polynomial
    freq : float
        Frequency at which to fit the template
    sums : Summations, optional
        Precomputed summations (C, S, CC, CS, SS, YC, YS). Default
        is None, which means the sums are computed directly (no NFFT)
    allow_negative_amplitudes : bool, optional, (default = True)
        Specifies whether or not negative amplitude solutions are allowed.
        They are automatically forbidden for H=1 (since this is equivalent
        to a phase shift). If no positive amplitude solutions are found and
        allow_negative_amplitudes = False, the periodogram is set to 0

    Returns
    -------
    power : float
        $(\chi^2_0 - \chi^2(fit)) / \chi^2_0$, where $\chi^2_0$ is for a
        flat model with $\hat{y}_0 = \bar{y}$, the weighted mean.
    params : ModelFitParams
        Best fit template parameters
    """
    nh   = len(cn)
    w    = weights(dy)
    ybar = np.dot(w, y)
    yy   = np.dot(w, (y - ybar)**2)

    if sums is None:
        sums   = direct_summations(t, y, w, freq, nh)

    if zeros is None:
        zeros = compute_zeros(ptensors, sums)

    # Check boundaries, too
    for edge in [1 - small, -1 + small]:
        if not edge in zeros:
            zeros.append(edge)

    power, params = None, None
    for b in zeros:
        for sgn in [-1, 1]:
            A = Avec(b, cn, sn, sgn=sgn)
            B = Bvec(b, cn, sn, sgn=sgn)

            AYCBYS = np.dot(A, sums.YC) + np.dot(B, sums.YS)
            ACBS   = np.dot(A, sums.C)  + np.dot(B, sums.S)

            D = np.dot(np.dot(A, sums.CC), A) + 2 * np.dot(np.dot(A, sums.CS), B)\
                 + np.dot(np.dot(B, sums.SS), B)

            # Obtain amplitude for a given b=cos(wtau) and sign(sin(wtau))
            a = AYCBYS / D

            # Skip negative amplitude solutions
            if a < 0 and (not allow_negative_amplitudes or nh == 1):
                continue

            # Compute periodogram
            p = a * AYCBYS / yy

            # Record the best-fit parameters for this template
            if power is None or p > power:

                # Get offset
                c = ybar - a * ACBS

                # Store best-fit parameters
                params = ModelFitParams(a=a, b=b, c=c, sgn=sgn)

                power = p

    if params is None:
        return 0, ModelFitParams(a=0, b=1, c=ybar, sgn=1)

    return power, params


def template_periodogram(t, y, dy, cn, sn, freqs, ptensors=None,
                        summations=None, allow_negative_amplitudes=True,
                        fast=True):
    r"""
    Produces a template periodogram using a single template

    Parameters
    ----------
    t : array_like
        Measurement times (must be monotonically increasing)
    y : array_like
        Measurement values at corresponding measurement times
    dy : array_like
        Measurement uncertainties
    cn : array_like
        Fourier (cosine) coefficients of the template
    sn : array_like
        Fourier (sine) coefficients of the template
    ptensors : np.ndarray, shape = (H, H, H, L), optional
        Polynomial coefficients from template; H is the number of
        harmonics, L is the (maximum) length of the polynomial
    freqs : array_like
        Frequencies at which to fit the template
    summations : list of Summations, optional
        Precomputed summations (C, S, CC, CS, SS, YC, YS) at each frequency
        in freqs. Default is None, which means the sums are computed via
        direct summations (if `fast=False`) or via fast summations (NFFT, if
        `fast=True`)
    allow_negative_amplitudes : bool, optional, (default = True)
        Specifies whether or not negative amplitude solutions are allowed.
        They are automatically forbidden for H=1 (since this is equivalent
        to a phase shift). If no positive amplitude solutions are found and
        allow_negative_amplitudes = False, the periodogram is set to 0

    Returns
    -------
    powers : array_like
        $(\chi^2_0 - \chi^2(fit)) / \chi^2_0$ at each frequency in `freqs`,
        where $\chi^2_0$ is for a flat model with $\hat{y}_0 = \bar{y}$,
        the weighted mean.
    best_fit_params : list of `ModelFitParams`
        List of best-fit model parameters at each frequency in `freqs`
    """
    nh = len(cn)
    w = weights(dy)

    if ptensors is None:
        pvectors = get_polynomial_vectors(cn, sn, sgn=1)
        ptensors = compute_polynomial_tensors(*pvectors)

    if summations is None:
        # compute sums using NFFT
        if fast:
            summations = fast_summations(t, y, w, freqs, nh)
        else:
            summations = direct_summations(t, y, w, freqs, nh)

    all_zeros = compute_zeros_multifrequency(ptensors, summations)
    powers, best_fit_params = [], []

    # Iterate through frequency values (sums contains C, S, YC, ...)
    for frq, sums, zeros in zip(freqs, summations, all_zeros):
        power, params = fit_template(t, y, dy, cn, sn, ptensors, frq, sums=sums,
                          allow_negative_amplitudes=allow_negative_amplitudes,
                          zeros=zeros)

        best_fit_params.append(params)
        powers.append(power)

    return np.array(powers), best_fit_params