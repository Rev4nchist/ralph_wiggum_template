export class StringUtils {
  /**
   * Reverses a string
   * @param str - The string to reverse
   * @returns The reversed string
   */
  reverse(str: string): string {
    return str.split('').reverse().join('');
  }

  /**
   * Capitalizes the first letter of each word in a string
   * @param str - The string to capitalize
   * @returns The string with each word capitalized
   */
  capitalize(str: string): string {
    if (str.length === 0) {
      return str;
    }

    return str
      .split(' ')
      .map(word => {
        if (word.length === 0) {
          return word;
        }
        return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
      })
      .join(' ');
  }

  /**
   * Counts the number of words in a string
   * @param str - The string to count words in
   * @returns The number of words
   */
  wordCount(str: string): number {
    if (str.trim().length === 0) {
      return 0;
    }

    return str.trim().split(/\s+/).length;
  }
}
