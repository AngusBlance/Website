#include <iostream>

class ForwardAutoDiff
{
public:
    double real;
    double dual;

    ForwardAutoDiff(double real, double dual = 0.0)
        : real(real), dual(dual) {}

    ForwardAutoDiff operator+(const ForwardAutoDiff& other) const {
        return ForwardAutoDiff(real + other.real, dual + other.dual);
    }

    ForwardAutoDiff operator*(const ForwardAutoDiff& other) const {
        return ForwardAutoDiff(
            real * other.real,
            real * other.dual + dual * other.real
        );
    }
};

typedef ForwardAutoDiff (*DiffFunc)(ForwardAutoDiff);

double diff(DiffFunc f, double x) {
    return f(ForwardAutoDiff(x, 1.0)).dual;
}

ForwardAutoDiff f(ForwardAutoDiff x) {
    return x * x + ForwardAutoDiff(6) * x + ForwardAutoDiff(-1);
}

int main()
{
    double x = 3;
    std::cout << diff(f, x) << std::endl;  // 12
    return 0;
}