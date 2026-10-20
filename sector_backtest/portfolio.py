def solve_capped_minimum_variance(covariance, *, max_weight=0.25, max_iterations=100000):
    """Solve a strictly convex long-only, fully invested, capped variance problem."""
    import hashlib
    import inspect
    import json
    import numbers
    import numpy as np
    import pandas as pd
    from pandas.api.types import is_bool_dtype, is_complex_dtype, is_numeric_dtype

    def require(condition, message):
        if not condition:
            raise ValueError(message)

    def fingerprint(value):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    require(isinstance(covariance, pd.DataFrame), "Covariance must be a DataFrame")
    assets = len(covariance)
    require(assets >= 2 and covariance.shape == (assets, assets),
            "Covariance must be square with at least two assets")
    labels = covariance.columns.tolist()
    require(covariance.columns.is_unique and covariance.index.tolist() == labels
            and all(isinstance(c, str) and c and c == c.strip() for c in labels),
            "Row and column labels must be identical, ordered, unique asset names")
    require(all(is_numeric_dtype(dtype) and not is_bool_dtype(dtype)
                and not is_complex_dtype(dtype) for dtype in covariance.dtypes),
            "Covariance must have real numeric dtypes")
    require(isinstance(max_weight, numbers.Real) and not isinstance(max_weight, (bool, np.bool_))
            and np.isfinite(max_weight) and 1.0 / assets <= max_weight <= 1.0,
            "Weight cap must be finite, at least 1/assets, and at most 1")
    require(isinstance(max_iterations, numbers.Integral)
            and not isinstance(max_iterations, (bool, np.bool_)) and max_iterations > 0,
            "max_iterations must be a positive integer")
    cap = float(max_weight)
    matrix = covariance.to_numpy(dtype=float, copy=True)
    require(np.isfinite(matrix).all() and np.array_equal(matrix, matrix.T),
            "Covariance must be finite and exactly symmetric")
    eigenvalues = np.linalg.eigvalsh(matrix)
    eps = np.finfo(float).eps
    pd_tolerance = 64 * assets * eps * float(np.max(np.abs(eigenvalues)))
    require(eigenvalues[0] > pd_tolerance,
            "Covariance must be numerically positive definite; no repair is applied")
    scale = float(np.max(np.diag(matrix)))
    hessian = matrix / scale
    feasibility_tolerance = 1e-12
    optimality_tolerance = 1e-10
    weights = np.full(assets, 1.0 / assets, dtype=float)
    unique_feasible = cap == 1.0 / assets

    # Each step transfers weight between two assets and minimizes along that line.
    for iteration in range(int(max_iterations) + 1):
        gradient = hessian @ weights
        donors = np.flatnonzero(weights > 0.0)
        receivers = np.flatnonzero(weights < cap)
        if unique_feasible:
            transfer_gap = 0.0
            break
        require(len(donors) > 0 and len(receivers) > 0,
                "No feasible transfer direction despite non-unique constraints")
        donor = int(donors[np.argmax(gradient[donors])])
        receiver = int(receivers[np.argmin(gradient[receivers])])
        transfer_gap = float(max(0.0, gradient[donor] - gradient[receiver]))
        if transfer_gap <= optimality_tolerance:
            break
        require(iteration < max_iterations, "Minimum-variance solver did not converge")
        curvature = float(hessian[receiver, receiver] + hessian[donor, donor]
                          - 2.0 * hessian[receiver, donor])
        require(curvature > 0 and np.isfinite(curvature), "Invalid transfer curvature")
        receiver_room = cap - weights[receiver]
        donor_weight = weights[donor]
        step = float(min(transfer_gap / curvature, receiver_room, donor_weight))
        require(np.isfinite(step) and step > 0, "No positive representable transfer step")
        previous = weights.copy()
        weights[receiver] += step
        weights[donor] -= step
        # Set only the bound reached by the feasible step, not a post-hoc projection.
        if step == receiver_room:
            weights[receiver] = cap
        if step == donor_weight:
            weights[donor] = 0.0
        require(not np.array_equal(previous, weights), "Solver stalled at floating-point precision")

    sum_error = float(abs(weights.sum() - 1.0))
    lower_error = float(max(0.0, -weights.min()))
    upper_error = float(max(0.0, weights.max() - cap))
    require(max(sum_error, lower_error, upper_error) <= feasibility_tolerance,
            "Final weights violate the portfolio constraints")

    # Minimize the linearized objective over the same capped simplex.
    gradient = hessian @ weights
    linear_minimizer = np.zeros(assets)
    remaining = 1.0
    for position in np.argsort(gradient, kind="stable"):
        allocation = min(cap, remaining)
        linear_minimizer[position] = allocation
        remaining -= allocation
        if remaining <= 0.0:
            break
    require(abs(remaining) <= feasibility_tolerance, "Linear certificate is infeasible")
    raw_duality_gap = float(gradient @ (weights - linear_minimizer))
    gap_roundoff_tolerance = float(64 * assets * eps * max(1.0, np.max(np.abs(gradient))))
    require(-gap_roundoff_tolerance <= raw_duality_gap <= optimality_tolerance,
            "Convex optimality-gap check failed")

    if unique_feasible:
        threshold = float(gradient.max())
    else:
        threshold = float((gradient[donors].max() + gradient[receivers].min()) / 2.0)
    lower = weights == 0.0
    upper = weights == cap
    free = ~(lower | upper)
    residuals = np.zeros(assets)
    residuals[lower] = np.maximum(threshold - gradient[lower], 0.0)
    residuals[upper] = np.maximum(gradient[upper] - threshold, 0.0)
    residuals[free] = np.abs(gradient[free] - threshold)
    kkt_residual = float(residuals.max())
    require(kkt_residual <= optimality_tolerance, "KKT gradient check failed")
    daily_variance = float(weights @ matrix @ weights)
    require(np.isfinite(daily_variance) and daily_variance > 0,
            "Invalid estimated portfolio variance")
    daily_gap = float(scale * (2.0 * max(0.0, raw_duality_gap)))
    require(np.isfinite(daily_gap), "Non-finite optimality-gap certificate")
    covariance_payload = {"columns": labels, "values": matrix.tolist()}
    weight_payload = {"tickers": labels, "weights": weights.tolist()}
    return {
        "schema_version": "capped_minimum_variance_solution_v1",
        "solver": "pairwise_exact_coordinate_descent",
        "tickers": labels, "weights": weights.tolist(),
        "covariance_sha256": fingerprint(covariance_payload),
        "weights_sha256": fingerprint(weight_payload),
        "constraints": {"long_only": True, "weight_sum": 1.0, "max_weight": cap},
        "iterations": iteration, "max_iterations": int(max_iterations),
        "unique_feasible_portfolio": unique_feasible,
        "objective": "minimize_w_transpose_covariance_w",
        "certificate_objective": "half_variance_divided_by_maximum_asset_variance",
        "objective_scale": scale,
        "estimated_daily_variance": daily_variance,
        "minimum_covariance_eigenvalue": float(eigenvalues[0]),
        "covariance_positive_definite_tolerance": pd_tolerance,
        "feasibility_tolerance": feasibility_tolerance,
        "optimality_tolerance_scaled": optimality_tolerance,
        "sum_error": sum_error, "lower_bound_error": lower_error, "upper_bound_error": upper_error,
        "transfer_gap_scaled": transfer_gap, "kkt_residual_scaled": kkt_residual,
        "kkt_threshold_scaled": threshold,
        "raw_duality_gap_scaled": raw_duality_gap,
        "gap_roundoff_tolerance_scaled": gap_roundoff_tolerance,
        "duality_gap_daily_variance_units": daily_gap,
        "lower_bound_assets": [labels[i] for i in np.flatnonzero(lower)],
        "upper_bound_assets": [labels[i] for i in np.flatnonzero(upper)],
        "constraints_verified": True, "kkt_verified": True, "duality_gap_verified": True,
        "covariance_repaired": False, "weights_postprocessed": False, "fallback_used": False,
        "implementation_sha256": hashlib.sha256(
            inspect.getsource(solve_capped_minimum_variance).encode("utf-8")
        ).hexdigest(),
        "versions": {"numpy": np.__version__, "pandas": pd.__version__},
    }