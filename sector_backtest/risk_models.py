def estimate_covariance_models(window_returns):
    """Estimate daily sample and Ledoit-Wolf constant-correlation covariances.

    Follows covCor.m, version 01/2021, default demeaning with n = T - 1.
    Reference: https://github.com/oledoit/covShrinkage/blob/main/covCor.m

    The reference implementation is released under the BSD 2-clause license:
    Copyright (c) 2014-2021, Olivier Ledoit and Michael Wolf
    All rights reserved.

    Redistribution and use in source and binary forms, with or without
    modification, are permitted provided that the following conditions are met:
    1. Redistributions of source code must retain the above copyright notice,
       this list of conditions and the following disclaimer.
    2. Redistributions in binary form must reproduce the above copyright
       notice, this list of conditions and the following disclaimer in the
       documentation and/or other materials provided with the distribution.

    THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS
    IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
    THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
    PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
    CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
    EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
    PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
    PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
    LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
    NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
    SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
    """
    import hashlib
    import inspect
    import json

    import numpy as np
    import pandas as pd
    from pandas.api.types import (
        is_bool_dtype,
        is_complex_dtype,
        is_numeric_dtype,
    )

    def require(condition, message):
        if not condition:
            raise ValueError(message)

    def fingerprint(value):
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
        )
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    require(
        isinstance(window_returns, pd.DataFrame),
        "Returns must be a DataFrame",
    )
    require(
        window_returns.shape[0] >= 3
        and window_returns.shape[1] >= 2,
        "At least three observations and two assets are required",
    )
    require(
        window_returns.columns.is_unique
        and all(
            isinstance(column, str)
            and column
            and column == column.strip()
            for column in window_returns.columns
        ),
        "Asset labels must be unique nonempty strings "
        "without surrounding whitespace",
    )

    dates = window_returns.index
    require(
        isinstance(dates, pd.DatetimeIndex)
        and dates.tz is None
        and not dates.hasnans
        and dates.is_unique
        and dates.is_monotonic_increasing
        and (dates == dates.normalize()).all(),
        "Returns need ordered unique timezone-naive daily session dates",
    )
    require(
        all(
            is_numeric_dtype(dtype)
            and not is_bool_dtype(dtype)
            and not is_complex_dtype(dtype)
            for dtype in window_returns.dtypes
        ),
        "Returns must have real numeric dtypes, "
        "not booleans or complex values",
    )

    values = window_returns.to_numpy(dtype=float, copy=True)
    require(
        np.isfinite(values).all()
        and (values > -1.0).all(),
        "Simple decimal returns must be finite and greater than -1",
    )
    require(
        (np.ptp(values, axis=0) > 0).all(),
        "An asset has zero variation in this window",
    )

    observations, assets = values.shape
    denominator = observations - 1
    eps = np.finfo(float).eps

    with np.errstate(over="raise", invalid="raise", divide="raise"):
        centered = values - values.mean(axis=0)

        # Sample covariance, using T - 1.
        sample = centered.T @ centered / denominator
        variances = np.diag(sample)

        require(
            np.isfinite(sample).all()
            and (variances > 0).all(),
            "Sample variances must be finite and positive",
        )

        # Constant-correlation target with unchanged sample variances.
        std = np.sqrt(variances)
        std_outer = np.outer(std, std)
        correlation = sample / std_outer

        average_correlation = float(
            (correlation.sum() - assets)
            / (assets * (assets - 1))
        )
        require(
            -1.0 / (assets - 1) - 64 * eps
            <= average_correlation
            <= 1.0 + 64 * eps,
            "Average correlation lies outside its valid range",
        )

        target = average_correlation * std_outer
        np.fill_diagonal(target, variances)

        # Ledoit-Wolf moment estimates, using the same denominator.
        squared = centered ** 2
        pi_matrix = (
            squared.T @ squared / denominator
            - sample ** 2
        )
        pi_hat = float(pi_matrix.sum())

        theta = (
            (centered ** 3).T @ centered / denominator
            - variances[:, None] * sample
        )
        np.fill_diagonal(theta, 0.0)

        rho_hat = float(
            np.trace(pi_matrix)
            + average_correlation
            * (
                (std[None, :] / std[:, None]) * theta
            ).sum()
        )

        distance = float(
            np.linalg.norm(sample - target, ord="fro")
        )
        sample_norm = float(
            np.linalg.norm(sample, ord="fro")
        )
        gamma_hat = distance ** 2

        require(
            np.isfinite(
                [pi_hat, rho_hat, gamma_hat, sample_norm]
            ).all()
            and sample_norm > 0,
            "Nonfinite or underflowed shrinkage moments",
        )

        # Avoid an undefined ratio when sample and target already coincide.
        target_equals_sample = (
            distance <= 64 * eps * sample_norm
        )

        if target_equals_sample:
            raw_shrinkage = None
            shrinkage = 0.0
        else:
            require(
                gamma_hat > 0,
                "Shrinkage distance underflowed",
            )
            raw_shrinkage = float(
                (pi_hat - rho_hat)
                / (denominator * gamma_hat)
            )
            require(
                np.isfinite(raw_shrinkage),
                "Nonfinite shrinkage intensity",
            )
            shrinkage = float(
                np.clip(raw_shrinkage, 0.0, 1.0)
            )

        shrunk = (
            (1.0 - shrinkage) * sample
            + shrinkage * target
        )

    matrices = {
        "sample_covariance": sample,
        "constant_correlation_target": target,
        "shrunk_covariance": shrunk,
    }
    diagnostics = {}

    for name, matrix in matrices.items():
        require(
            np.isfinite(matrix).all()
            and np.array_equal(matrix, matrix.T),
            "Nonfinite or asymmetric matrix: " + name,
        )

        eigenvalues = np.linalg.eigvalsh(matrix)
        psd_tolerance = (
            64 * assets * eps
            * float(np.max(np.abs(eigenvalues)))
        )

        require(
            float(eigenvalues[0]) >= -psd_tolerance,
            "Matrix is not positive semidefinite within roundoff: "
            + name,
        )

        positive_definite = bool(
            eigenvalues[0] > psd_tolerance
        )
        diagnostics[name] = {
            "minimum_eigenvalue": float(eigenvalues[0]),
            "maximum_eigenvalue": float(eigenvalues[-1]),
            "psd_roundoff_tolerance": psd_tolerance,
            "positive_semidefinite_within_tolerance": True,
            "numerically_positive_definite": positive_definite,
            "spectral_condition_number": (
                float(eigenvalues[-1] / eigenvalues[0])
                if positive_definite else None
            ),
        }

    require(
        np.allclose(
            np.diag(shrunk),
            variances,
            rtol=64 * eps,
            atol=0,
        ),
        "Shrinkage failed to preserve sample variances",
    )

    columns = window_returns.columns.tolist()
    payloads = {
        name: {
            "columns": columns,
            "values": matrix.tolist(),
        }
        for name, matrix in matrices.items()
    }

    input_payload = {
        "index_name": "session_date",
        "dates": dates.strftime("%Y-%m-%d").tolist(),
        "columns": columns,
        "values": values.tolist(),
    }

    return {
        "schema_version": "constant_correlation_covariance_models_v1",
        "observations": observations,
        "assets": assets,
        "tickers": columns,
        "first_session": input_payload["dates"][0],
        "last_session": input_payload["dates"][-1],
        "input_returns_sha256": fingerprint(input_payload),
        "covariance_units": "daily_decimal_return_squared",
        "annualized": False,
        "demeaned_inside_window": True,
        "degrees_of_freedom_removed": 1,
        "moment_denominator": denominator,
        "shrinkage_denominator": denominator,
        "method_variant": "author_covCor_2021_default_demeaning",
        "average_correlation": average_correlation,
        "pi_hat": pi_hat,
        "rho_hat": rho_hat,
        "gamma_hat": gamma_hat,
        "raw_shrinkage_intensity": raw_shrinkage,
        "shrinkage_intensity": shrinkage,
        "target_equals_sample_within_roundoff": bool(
            target_equals_sample
        ),
        "degenerate_target_policy": (
            "delta_zero_when_frobenius_distance_at_most_"
            "64eps_times_sample_norm"
        ),
        "matrix_eigenvalues_repaired": False,
        "diagonal_jitter_added": False,
        **payloads,
        "matrix_sha256": {
            name: fingerprint(payload)
            for name, payload in payloads.items()
        },
        "diagnostics": diagnostics,
        "matrix_checks_passed": True,
        "reference_code": (
            "https://github.com/oledoit/covShrinkage/blob/main/covCor.m"
        ),
        "reference_code_version": "01/2021",
        "reference_checked_on": "2026-10-16",
        "serial_dependence_correction": "none",
        "implementation_sha256": hashlib.sha256(
            inspect.getsource(
                estimate_covariance_models
            ).encode("utf-8")
        ).hexdigest(),
        "versions": {
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
    }