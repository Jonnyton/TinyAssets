import { expect, test } from '@playwright/test';

test('landing page loads with three CTAs', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByText('Summon the daemon.')).toBeVisible();
  await expect(page.getByText('Try in Claude.ai (zero-install)')).toBeVisible();
  await expect(page.getByText('Host a daemon (one-click)')).toBeVisible();
  await expect(page.getByText('Contribute to the OSS core')).toBeVisible();
});

test('connect page shows the MCP URL + copy button', async ({ page }) => {
  await page.goto('/connect');
  await expect(page.getByText('https://tinyassets.io/mcp')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Copy URL' })).toBeVisible();
});

test('catalog page loads', async ({ page }) => {
  await page.goto('/catalog');
  await expect(page.getByRole('heading', { name: 'TinyAssets Catalog' })).toBeVisible();
});

test('status page renders widgets', async ({ page }) => {
  await page.goto('/status');
  await expect(page.getByText('Hosts online')).toBeVisible();
  await expect(page.getByText('Pending requests')).toBeVisible();
});
