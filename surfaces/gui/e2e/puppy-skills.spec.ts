import { readFileSync } from 'node:fs';
import { test, expect } from './fixtures';

const picks = JSON.parse(readFileSync(new URL('../../../coworker/skills/store_extras.json', import.meta.url), 'utf8'))
  .filter((entry: { recommended?: boolean }) => entry.recommended);

test('recommended skills are discoverable and clearing search returns to the shelf', async ({ page }) => {
  await page.route('**/v1/skills/store/categories', r => r.fulfill({json:{categories:[{key:'recommended',label:'Recommended',count:picks.length}]}}));
  await page.route('**/v1/skills/store?*', r => {
    const q = new URL(r.request().url()).searchParams.get('q');
    const results = q ? picks.filter((e: {name:string}) => e.name.includes(q)) : picks;
    return r.fulfill({json:{results,total:results.length,offset:0}});
  });
  await page.goto('/');
  await page.getByTestId('account-row').click();
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  await page.getByRole('button',{name:'Skills',exact:true}).click();
  await page.getByRole('button',{name:/Add skill/}).click();
  await page.getByTestId('skill-store-open').click();
  await expect(page.getByTestId('skill-store-shelf-recommended')).toHaveAttribute('aria-pressed','true');
  await expect(page.getByTestId('skill-store-install-sepia')).toBeVisible();
  await page.getByRole('textbox',{name:'Search the skill store'}).fill('sepia');
  await expect(page.getByTestId('skill-store-install-theme-factory')).toHaveCount(0);
  await page.getByRole('button',{name:'Clear search'}).click();
  await expect(page.getByTestId('skill-store-install-theme-factory')).toBeVisible();
  for (const width of [1280, 980, 768, 1920]) {
    await page.setViewportSize({width,height:900});
    await page.screenshot({path:`/tmp/mimi-audit-store-after-${width}.png`});
  }
});

test('Puppy shows the daily allowance before it is low', async ({ page }) => {
  await page.route('**/v1/settings', r => r.fulfill({json:{model:'qualitati:mimi-puppy',models:['qualitati:mimi-puppy'],model_labels:{'qualitati:mimi-puppy':'Mimi Puppy'},has_key:true,model_ready:true,onboarded:true,nav_layout:'flat'}}));
  await page.route('**/v1/qualitati/status', r => r.fulfill({json:{ok:true,signed_in:true,profile:{username:'Demo',credits:420},free_tier:{model:'mimi-puppy',cap:500,remaining:300,resets_at:'2026-09-06T00:00:00Z'}}}));
  await page.goto('/');
  await page.getByRole('button', {name:'claude-opus-4-8',exact:true}).click();
  await page.locator('.dd-item').filter({hasText:'Mimi Puppy'}).click();
  await expect(page.getByTestId('free-tier-banner')).toContainText('300 free requests left today (daily limit: 500)');
  await page.setViewportSize({width:1280,height:900});
  await page.screenshot({path:'/tmp/mimi-audit-puppy-after.png'});
});
