try:
    import numpy as np
    from scipy.optimize import minimize
    from scipy.stats import beta
except Exception:
    np = None
    minimize = None
    beta = None


class SCurve:
    def __init__(self, a, b, c, s, lut_points=33):
        if np is None or minimize is None or beta is None:
            raise RuntimeError("numpy/scipy required for SCurve")
        if not (0 <= a < c < b <= 1):
            raise ValueError("params must satisfy 0 <= a < c < b <= 1")
        self.a = a
        self.b = b
        self.c = c
        self.s = s
        self.lut_points = lut_points
        self._alpha, self._beta = self._solve_params()
        self.lut_table = self._generate_lut()

    def _solve_params(self):
        z_c = (self.c - self.a) / (self.b - self.a)

        def error_function(params):
            alpha_p, beta_p = params
            if alpha_p <= 0 or beta_p <= 0:
                return 1e9
            err1 = beta.cdf(z_c, alpha_p, beta_p) - 0.5
            err2 = beta.pdf(z_c, alpha_p, beta_p) / (self.b - self.a) - self.s
            return err1**2 + 0.1 * err2**2

        result = minimize(
            error_function,
            [1.0, 1.0],
            method="L-BFGS-B",
            bounds=[(0.01, None), (0.01, None)],
        )
        if not result.success:
            raise RuntimeError(
                f"optimizer failed for a={self.a}, b={self.b}, c={self.c}, s={self.s}"
            )
        return result.x

    def _generate_lut(self):
        x_lut_int = np.array(
            [int(round(1023 * i / (self.lut_points - 1))) for i in range(self.lut_points)]
        )
        y_lut_int_float = self.evaluate_true(x_lut_int)
        return np.round(np.clip(y_lut_int_float, 0, 1023)).astype(np.uint16)

    def evaluate_true(self, x_int):
        x_float = self.a + (self.b - self.a) * np.array(x_int) / 1023.0
        z_float = np.clip((x_float - self.a) / (self.b - self.a), 0.0, 1.0)
        y_float_0_1 = beta.cdf(z_float, a=self._alpha, b=self._beta)
        return y_float_0_1 * 1023.0


def generate_lut_values(a_int, b_int, c_int, lut_points=33):
    a_int = int(a_int)
    b_int = int(b_int)
    c_int = int(c_int)
    if not (a_int < c_int < b_int):
        raise ValueError("params must satisfy a < c < b")
    span = b_int - a_int
    c_norm = (c_int - a_int) / span
    if not (0.0 < c_norm < 1.0):
        raise ValueError("mid must be between min and max")
    s1 = 0.5 / c_norm
    s2 = 0.5 / (1.0 - c_norm)
    s = (s1 + s2) / 2
    curve = SCurve(a=0.0, b=1.0, c=c_norm, s=s, lut_points=lut_points)

    lut = []
    for i in range(lut_points):
        x = int(round(1023 * i / (lut_points - 1)))
        if x <= a_int:
            lut.append(0)
            continue
        if x >= b_int:
            lut.append(1023)
            continue
        z = (x - a_int) / span
        y = curve.evaluate_true(int(round(z * 1023)))
        lut.append(int(round(y)))
    return lut


class AxisCalibrator:
    def __init__(self, name, is_brake=False):
        self.name = name
        self.is_brake = is_brake
        self.min_val = 0
        self.mid_val = 512
        self.max_val = 1023

    def set_points(self, min_val, mid_val, max_val):
        min_val, max_val = sorted([int(min_val), int(max_val)])
        if max_val - min_val < 2:
            self.min_val, self.mid_val, self.max_val = 0, 512, 1023
            return
        mid_val = int(round(mid_val))
        mid_val = max(min_val + 1, min(mid_val, max_val - 1))
        self.min_val = min_val
        self.mid_val = mid_val
        self.max_val = max_val

    def _piecewise_linear_lut(self):
        lut = []
        for i in range(33):
            x = int(round(1023 * i / 32))
            if x <= self.mid_val:
                denom = self.mid_val - self.min_val
                t = 0 if denom == 0 else (x - self.min_val) / denom
                y = int(round(t * 512))
            else:
                denom = self.max_val - self.mid_val
                t = 0 if denom == 0 else (x - self.mid_val) / denom
                y = int(round(512 + t * 511))
            lut.append(max(0, min(1023, y)))
        return lut

    def _brake_linear_lut_with_deadzone(self, low_ratio=0.05, high_ratio=0.1):
        min_val = int(self.min_val)
        max_val = int(self.max_val)
        span = max_val - min_val
        if span < 2:
            return [int(round(1023 * i / 32)) for i in range(33)]
        dead_low = min_val + int(round(span * low_ratio))
        dead_high = max_val - int(round(span * high_ratio))
        if dead_high <= dead_low:
            dead_low = min_val
            dead_high = max_val
        lut = []
        for i in range(33):
            x = int(round(1023 * i / 32))
            if x <= min_val:
                lut.append(0)
                continue
            if x >= max_val:
                lut.append(1023)
                continue
            if x <= dead_low:
                lut.append(0)
                continue
            if x >= dead_high:
                lut.append(1023)
                continue
            t = (x - dead_low) / (dead_high - dead_low)
            y = int(round(t * 1023))
            lut.append(max(0, min(1023, y)))
        return lut

    def generate_33_lut(self):
        if self.is_brake:
            return self._brake_linear_lut_with_deadzone(0.05, 0.1)
        try:
            return generate_lut_values(self.min_val, self.max_val, self.mid_val, 33)
        except Exception as exc:
            print(f"[Calib] {self.name} fallback linear LUT: {exc}")
            return self._piecewise_linear_lut()
