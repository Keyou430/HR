import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("portal workbench refinement contracts", async () => {
  const appSource = await readFile(new URL("../src/app.js", import.meta.url), "utf-8");
  const htmlSource = await readFile(new URL("../index.html", import.meta.url), "utf-8");

  // Service category filtering
  assert.ok(appSource.includes("_serviceCategory"), "missing _serviceCategory state");
  assert.ok(appSource.includes("bindServiceMenu"), "missing bindServiceMenu function");

  // Document assistant
  assert.ok(appSource.includes("renderWorkspaceAssistant"), "missing renderWorkspaceAssistant function");
  assert.ok(htmlSource.includes("assistantStream"), "missing assistantStream element");
  assert.ok(htmlSource.includes("assistantRecentDocs"), "missing assistantRecentDocs element");
  assert.ok(htmlSource.includes("连接飞书文档"), "missing Feishu connect button");

  // Admin news tab
  assert.ok(htmlSource.includes('data-admin-panel="news"'), "missing admin news sub-tab");
  assert.ok(appSource.includes("fetchAdminNews"), "missing fetchAdminNews function");

  // Notice publish
  assert.ok(appSource.includes("canPublishNotices"), "missing canPublishNotices function");
  assert.ok(appSource.includes("openNoticePublishModal"), "missing openNoticePublishModal function");
  assert.ok(htmlSource.includes("noticePublishModal"), "missing noticePublishModal element");
});
