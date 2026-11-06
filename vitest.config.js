import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['tests/js/**/*.test.js'],
    testTimeout: 30000,
    hookTimeout: 60000,
  },
});
