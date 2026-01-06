import { StringUtils } from '../src/strings';

describe('StringUtils', () => {
  let stringUtils: StringUtils;

  beforeEach(() => {
    stringUtils = new StringUtils();
  });

  describe('reverse', () => {
    test('should reverse a simple string', () => {
      expect(stringUtils.reverse('hello')).toBe('olleh');
    });

    test('should reverse a string with spaces', () => {
      expect(stringUtils.reverse('hello world')).toBe('dlrow olleh');
    });

    test('should reverse an empty string', () => {
      expect(stringUtils.reverse('')).toBe('');
    });

    test('should reverse a single character', () => {
      expect(stringUtils.reverse('a')).toBe('a');
    });

    test('should reverse a string with special characters', () => {
      expect(stringUtils.reverse('hello!')).toBe('!olleh');
    });
  });

  describe('capitalize', () => {
    test('should capitalize first letter of a single word', () => {
      expect(stringUtils.capitalize('hello')).toBe('Hello');
    });

    test('should capitalize first letter of each word', () => {
      expect(stringUtils.capitalize('hello world')).toBe('Hello World');
    });

    test('should handle already capitalized words', () => {
      expect(stringUtils.capitalize('HELLO WORLD')).toBe('Hello World');
    });

    test('should handle mixed case words', () => {
      expect(stringUtils.capitalize('hELLo WoRLd')).toBe('Hello World');
    });

    test('should handle empty string', () => {
      expect(stringUtils.capitalize('')).toBe('');
    });

    test('should handle multiple spaces between words', () => {
      expect(stringUtils.capitalize('hello  world')).toBe('Hello  World');
    });

    test('should handle single character', () => {
      expect(stringUtils.capitalize('a')).toBe('A');
    });
  });

  describe('wordCount', () => {
    test('should count words in a simple sentence', () => {
      expect(stringUtils.wordCount('hello world')).toBe(2);
    });

    test('should count single word', () => {
      expect(stringUtils.wordCount('hello')).toBe(1);
    });

    test('should return 0 for empty string', () => {
      expect(stringUtils.wordCount('')).toBe(0);
    });

    test('should return 0 for whitespace-only string', () => {
      expect(stringUtils.wordCount('   ')).toBe(0);
    });

    test('should handle multiple spaces between words', () => {
      expect(stringUtils.wordCount('hello   world   test')).toBe(3);
    });

    test('should handle leading and trailing spaces', () => {
      expect(stringUtils.wordCount('  hello world  ')).toBe(2);
    });

    test('should count many words', () => {
      expect(stringUtils.wordCount('the quick brown fox jumps over the lazy dog')).toBe(9);
    });

    test('should handle tabs and newlines as whitespace', () => {
      expect(stringUtils.wordCount('hello\tworld\ntest')).toBe(3);
    });
  });
});
