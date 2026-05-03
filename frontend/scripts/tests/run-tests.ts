#!/usr/bin/env npx tsx
/**
 * Test Runner
 * Main entry point for running all tests or specific test suites
 */

import { execFileSync } from 'child_process';
import { readdirSync } from 'fs';
import * as path from 'path';

const frontendRoot = path.resolve(__dirname, '../..');
const nodeTestsDir = path.join(frontendRoot, 'src', '__tests__');
const nodeTestSetup = './src/__tests__/node-test-setup.ts';
const tsxBin = path.join(
  frontendRoot,
  'node_modules',
  '.bin',
  process.platform === 'win32' ? 'tsx.cmd' : 'tsx',
);

const testSuites = {
  'integrated': {
    name: 'Integrated Test Suite',
    description: 'Comprehensive test suite covering all major features',
    script: './integrated-test-suite.ts'
  },
  'router': {
    name: 'Router Agent Test',
    description: 'Tests routing logic for different query types',
    script: './router-agent-test.ts'
  },
  'calendar': {
    name: 'Calendar Integration Test',
    description: 'Tests Google Calendar integration',
    script: './calendar-integration-test.ts'
  }
};

const nodeTestSuite = {
  name: 'Node Test Suite',
  description: 'Discovers and runs src/__tests__/**/*.test.ts via node:test'
};

function printUsage() {
  console.log(`
Engineer Cafe Navigator - Test Runner
====================================

Usage: pnpm test:run [suite]

Available test suites:
`);
  
  Object.entries(testSuites).forEach(([key, suite]) => {
    console.log(`  ${key.padEnd(12)} - ${suite.description}`);
  });
  console.log(`  ${'node'.padEnd(12)} - ${nodeTestSuite.description}`);
  
  console.log(`
Run all tests:
  pnpm test

Run specific test:
  pnpm test integrated
  pnpm test router
  pnpm test calendar
  pnpm test node
`);
}

function discoverNodeTestFiles(dir = nodeTestsDir): string[] {
  return readdirSync(dir, { withFileTypes: true })
    .flatMap((entry) => {
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        return discoverNodeTestFiles(fullPath);
      }
      if (!entry.isFile() || !entry.name.endsWith('.test.ts')) {
        return [];
      }
      return [path.relative(frontendRoot, fullPath)];
    })
    .sort();
}

function runNodeTests() {
  const files = discoverNodeTestFiles();

  if (files.length === 0) {
    console.log('\nNo node:test files found in src/__tests__');
    return;
  }

  console.log(`\n🚀 Running ${nodeTestSuite.name}...`);
  console.log('='.repeat(60));
  console.log(`Discovered ${files.length} node:test file(s):`);
  files.forEach((file) => console.log(`  - ${file}`));

  execFileSync(tsxBin, ['--test', '--import', nodeTestSetup, ...files], {
    stdio: 'inherit',
    cwd: frontendRoot,
  });
}

async function runTest(suiteName: string) {
  if (suiteName === 'node') {
    try {
      runNodeTests();
    } catch (error) {
      console.error(`\n❌ Test suite failed: ${suiteName}`);
      process.exit(1);
    }
    return;
  }

  const suite = testSuites[suiteName as keyof typeof testSuites];
  
  if (!suite) {
    console.error(`❌ Unknown test suite: ${suiteName}`);
    printUsage();
    process.exit(1);
  }
  
  console.log(`\n🚀 Running ${suite.name}...`);
  console.log('=' .repeat(60));
  
  try {
    execFileSync(tsxBin, [suite.script], {
      stdio: 'inherit',
      cwd: __dirname
    });
  } catch (error) {
    console.error(`\n❌ Test suite failed: ${suiteName}`);
    process.exit(1);
  }
}

async function runAllTests() {
  console.log('🚀 Running All Test Suites');
  console.log('=' .repeat(60));
  
  let failedSuites: string[] = [];
  
  for (const [key, suite] of Object.entries(testSuites)) {
    console.log(`\n\n📋 ${suite.name}`);
    console.log('-'.repeat(60));
    
    try {
      execFileSync(tsxBin, [suite.script], {
        stdio: 'inherit',
        cwd: __dirname
      });
    } catch (error) {
      failedSuites.push(key);
    }
  }

  console.log(`\n\n📋 ${nodeTestSuite.name}`);
  console.log('-'.repeat(60));

  try {
    runNodeTests();
  } catch (error) {
    failedSuites.push('node');
  }
  
  console.log('\n\n' + '='.repeat(60));
  console.log('📊 TEST SUMMARY');
  console.log('='.repeat(60));
  
  if (failedSuites.length === 0) {
    console.log('✅ All test suites passed!');
  } else {
    console.log(`❌ ${failedSuites.length} test suite(s) failed:`);
    failedSuites.forEach(suite => {
      if (suite === 'node') {
        console.log(`   - ${nodeTestSuite.name}`);
      } else {
        console.log(`   - ${testSuites[suite as keyof typeof testSuites].name}`);
      }
    });
    process.exit(1);
  }
}

// Main execution
async function main() {
  const args = process.argv.slice(2);
  
  if (args.length === 0) {
    // Run all tests
    await runAllTests();
  } else if (args[0] === '--help' || args[0] === '-h') {
    printUsage();
  } else {
    // Run specific test
    await runTest(args[0]);
  }
}

if (require.main === module) {
  main().catch(error => {
    console.error('Test runner failed:', error);
    process.exit(1);
  });
}
