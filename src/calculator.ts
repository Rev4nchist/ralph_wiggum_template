/**
 * Calculator class providing basic arithmetic operations
 */
export class Calculator {
  /**
   * Add two numbers
   */
  add(a: number, b: number): number {
    return a + b;
  }

  /**
   * Subtract second number from first
   */
  subtract(a: number, b: number): number {
    return a - b;
  }

  /**
   * Multiply two numbers
   */
  multiply(a: number, b: number): number {
    return a * b;
  }

  /**
   * Divide first number by second
   * @throws {Error} When dividing by zero
   */
  divide(a: number, b: number): number {
    if (b === 0) {
      throw new Error('Cannot divide by zero');
    }
    return a / b;
  }
}
