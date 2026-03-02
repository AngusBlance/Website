class Differentiator:
    def __init__(self, func):
        self.func = func

    def finite_difference(self, x, h=0.001):
        numerator = self.func(x + h) - self.func(x)
        return numerator / h


def square(x):
    return x**2


def cube(x):
    return x**3


sq_diff = Differentiator(square)
print(f"Derivative of x^2 at 2: {sq_diff.finite_difference(2)}")


cube_diff = Differentiator(cube)
print(f"Derivative of x^3 at 2: {cube_diff.finite_difference(2)}")
