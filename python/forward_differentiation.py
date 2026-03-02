class ForwardAutoDiff:
    def __init__(self, real, dual):
        self.real = real
        self.dual = dual

    def __add__(self, other):
        real = self.real + other.real
        dual = self.dual + other.dual
        return ForwardAutoDiff(real, dual)

    def __mul__(self, other):
        real = self.real * other.real
        dual = self.real * other.dual + self.dual * other.real
        return ForwardAutoDiff(real, dual)


def diff(f, x):
    return f(ForwardAutoDiff(x, 1)).dual


def f(x):
    return x * x + ForwardAutoDiff(6, 0) * x + ForwardAutoDiff(-1, 0)


if __name__ == "__main__":
    x = 3
    print(diff(f, x))  # expected: 2x + 6 = 12
