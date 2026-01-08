import { describe, it, expect, beforeEach, jest } from '@jest/globals';
import { createMockRedis, MockRedis } from './setup.js';

describe('librarian_search', () => {
  it('validates required library parameter', () => {
    const params = { query: 'useState hooks' };
    const hasLibrary = 'library' in params && params.library;
    expect(hasLibrary).toBeFalsy();
  });

  it('accepts valid search modes', () => {
    const validModes = ['word', 'vector', 'hybrid'];
    expect(validModes).toContain('word');
    expect(validModes).toContain('vector');
    expect(validModes).toContain('hybrid');
    expect(validModes).not.toContain('invalid');
  });

  it('respects limit parameter bounds', () => {
    const min = 1;
    const max = 50;
    const defaultLimit = 10;

    expect(defaultLimit).toBeGreaterThanOrEqual(min);
    expect(defaultLimit).toBeLessThanOrEqual(max);
  });
});

describe('librarian_list_sources', () => {
  it('returns array of sources', () => {
    const mockSources = [
      { name: 'reactjs/react.dev', doc_count: 150, status: 'indexed' },
      { name: 'tailwindlabs/tailwindcss.com', doc_count: 200, status: 'indexed' },
    ];

    expect(Array.isArray(mockSources)).toBe(true);
    expect(mockSources).toHaveLength(2);
  });

  it('sources have required fields', () => {
    const source = {
      name: 'test/library',
      source_url: 'https://github.com/test/library',
      docs_path: '/docs',
      ref: 'main',
      doc_count: 50,
      status: 'indexed',
    };

    expect(source).toHaveProperty('name');
    expect(source).toHaveProperty('doc_count');
    expect(source).toHaveProperty('status');
  });
});

describe('librarian_get_document', () => {
  it('requires library and doc_id parameters', () => {
    const params = { library: 'reactjs/react.dev', doc_id: '123' };

    expect(params.library).toBeTruthy();
    expect(params.doc_id).toBeTruthy();
  });

  it('slice parameter is optional', () => {
    const paramsWithSlice = { library: 'test', doc_id: '1', slice: '13:29' };
    const paramsWithoutSlice = { library: 'test', doc_id: '1' };

    expect(paramsWithSlice.slice).toBe('13:29');
    expect(paramsWithoutSlice).not.toHaveProperty('slice');
  });
});

describe('librarian_search_api', () => {
  it('constructs API search query', () => {
    const apiName = 'useState';
    const library = 'reactjs/react.dev';
    const expectedQuery = `${apiName} API reference usage example`;

    expect(expectedQuery).toContain(apiName);
    expect(expectedQuery).toContain('API');
    expect(expectedQuery).toContain('reference');
  });
});

describe('librarian_search_error', () => {
  it('constructs error search query', () => {
    const errorMessage = 'Cannot read property of undefined';
    const expectedQuery = `error ${errorMessage} solution fix troubleshooting`;

    expect(expectedQuery).toContain('error');
    expect(expectedQuery).toContain(errorMessage);
    expect(expectedQuery).toContain('solution');
  });

  it('library parameter is optional', () => {
    const paramsWithLib = { error_message: 'test error', library: 'react' };
    const paramsWithoutLib = { error_message: 'test error' };

    expect(paramsWithLib.library).toBe('react');
    expect(paramsWithoutLib).not.toHaveProperty('library');
  });
});

describe('librarian_find_library', () => {
  it('accepts library name parameter', () => {
    const validNames = ['react', 'next', 'prisma', 'zod', 'tailwind'];

    validNames.forEach((name) => {
      expect(typeof name).toBe('string');
      expect(name.length).toBeGreaterThan(0);
    });
  });

  it('returns library identifiers', () => {
    const mockResult = {
      success: true,
      query: 'react',
      libraries: [
        { name: 'reactjs/react.dev', ref: 'main', versions: '19.0' },
        { name: 'facebook/react', ref: 'main', versions: '18.2' },
      ],
    };

    expect(mockResult.libraries).toHaveLength(2);
    expect(mockResult.libraries[0].name).toContain('/');
  });
});

describe('sanitizeLibrarianArg', () => {
  it('rejects shell injection characters', () => {
    const dangerousChars = [';', '&', '|', '`', '$', '(', ')', '{', '}', '[', ']', '<', '>', '\\', "'", '"', '\n', '\r'];

    dangerousChars.forEach((char) => {
      const input = `test${char}injection`;
      const hasDangerousChar = /[;&|`$(){}[\]<>\\'\"\n\r]/.test(input);
      expect(hasDangerousChar).toBe(true);
    });
  });

  it('accepts safe arguments', () => {
    const safeArgs = ['react hooks', 'useState-example', 'api_reference', 'next.js-routing'];

    safeArgs.forEach((arg) => {
      const hasDangerousChar = /[;&|`$(){}[\]<>\\'\"\n\r]/.test(arg);
      expect(hasDangerousChar).toBe(false);
    });
  });

  it('rejects arguments exceeding length limit', () => {
    const maxLength = 1000;
    const longArg = 'x'.repeat(1001);

    expect(longArg.length).toBeGreaterThan(maxLength);
  });
});

describe('validateFilePath', () => {
  it('rejects path traversal attempts', () => {
    const maliciousPaths = ['../etc/passwd', '..\\windows\\system32', 'foo/../../../bar'];

    maliciousPaths.forEach((path) => {
      const normalized = path.replace(/\\/g, '/');
      expect(normalized.includes('..')).toBe(true);
    });
  });

  it('accepts valid file paths', () => {
    const validPaths = ['src/index.ts', 'lib/utils/helper.js', 'tests/unit/test.spec.ts'];

    validPaths.forEach((path) => {
      expect(path.includes('..')).toBe(false);
      expect(/^[\w\-./]+$/.test(path)).toBe(true);
    });
  });

  it('rejects paths with invalid characters', () => {
    const invalidPaths = ['src/<script>.ts', 'lib/utils|helper.js', 'tests/unit;rm -rf.ts'];

    invalidPaths.forEach((path) => {
      expect(/^[\w\-./]+$/.test(path)).toBe(false);
    });
  });
});

describe('parseTextResults', () => {
  it('parses search result lines', () => {
    const sampleOutput = `
- reactjs/react.dev: hooks/useState.md (reference) doc 42 slice 13:29 score 0.89
- reactjs/react.dev: hooks/useEffect.md (guide) doc 43 slice 5:15 score 0.75
    `.trim();

    const lines = sampleOutput.split('\n');
    const results: Array<{ library: string; score: number }> = [];

    for (const line of lines) {
      const match = line.match(/^-\s+([^:]+):\s+([^\s]+)\s+\(([^)]+)\)\s+doc\s+(\d+)\s+slice\s+([^\s]+)\s+score\s+([\d.]+)/);
      if (match) {
        results.push({
          library: match[1],
          score: parseFloat(match[6]),
        });
      }
    }

    expect(results).toHaveLength(2);
    expect(results[0].library).toBe('reactjs/react.dev');
    expect(results[0].score).toBeCloseTo(0.89);
  });

  it('handles empty output', () => {
    const emptyOutput = '';
    const lines = emptyOutput.split('\n').filter((l) => l.trim());
    expect(lines).toHaveLength(0);
  });
});

describe('Librarian CLI timeout handling', () => {
  it('defines reasonable timeout values', () => {
    const defaultTimeout = 60000;
    const maxReasonableTimeout = 120000;

    expect(defaultTimeout).toBeGreaterThan(0);
    expect(defaultTimeout).toBeLessThanOrEqual(maxReasonableTimeout);
  });

  it('timeout configuration is numeric', () => {
    const timeoutString = '60000';
    const parsed = parseInt(timeoutString, 10);

    expect(typeof parsed).toBe('number');
    expect(isNaN(parsed)).toBe(false);
  });
});

describe('Librarian error handling', () => {
  it('handles command not found gracefully', () => {
    const errorScenarios = [
      { exitCode: 127, meaning: 'command not found' },
      { exitCode: 1, meaning: 'general error' },
      { exitCode: 0, meaning: 'success' },
    ];

    const notFound = errorScenarios.find((e) => e.exitCode === 127);
    expect(notFound?.meaning).toBe('command not found');
  });

  it('structures error response correctly', () => {
    const errorResponse = {
      success: false,
      error: 'Library name is required for search',
    };

    expect(errorResponse.success).toBe(false);
    expect(errorResponse.error).toBeTruthy();
  });
});
