export function helloWorld(): string {
  return "Hello, World!";
}

// Run hello world when executed directly
if (require.main === module) {
  console.log(helloWorld());
}
