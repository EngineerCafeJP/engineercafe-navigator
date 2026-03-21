#!/usr/bin/env node
/**
 * Calendar integration smoke test.
 *
 * Verifies the backend calendar endpoint through the shared backend proxy
 * helper so frontend-side calendar access no longer depends on a direct iCal
 * URL.
 */

import 'dotenv/config';
import { backendFetch } from '../../src/lib/api/backend-proxy';

export async function testCalendarIntegration() {
  console.log('📅 Testing calendar backend proxy integration\n');

  if (!process.env.BACKEND_API_URL) {
    console.log('❌ BACKEND_API_URL is not configured in environment');
    return {
      success: false,
      error: 'Backend URL not configured',
    };
  }

  try {
    const result = await backendFetch('/api/calendar', {
      method: 'GET',
    });

    if (result.ok) {
      console.log('✅ Calendar proxy request successful!');
      console.log('\nCalendar response:');
      console.log(result.data);
      return {
        success: true,
        data: result.data,
      };
    }

    console.log('❌ Calendar proxy request failed');
    console.log(`   Status: ${result.status}`);
    console.log(`   Error: ${JSON.stringify(result.data)}`);
    return {
      success: false,
      error: result.data,
    };
  } catch (error) {
    console.log('❌ Exception during calendar proxy request');
    console.log(`   Error: ${error instanceof Error ? error.message : 'Unknown error'}`);
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Unknown error',
    };
  }
}

if (require.main === module) {
  testCalendarIntegration().catch(console.error);
}
