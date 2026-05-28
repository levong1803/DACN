/**
 * Dữ liệu OWASP WSTG Checklist - Trích xuất tự động từ OWASP_WSTG_Checklist.xlsx
 * 12 hạng mục, 105 test case chính xác theo chuẩn OWASP WSTG v4.2
 */
import rawData from "./wstg_extracted.json";

/**
 * Sinh prompt tự động dựa trên 16 tools có sẵn trong hệ thống:
 * nmap, dirb, hydra, sqlmap, nikto, whatweb, wafw00f, dnsrecon,
 * testssl, curl, commix, wfuzz, tplmap, zaproxy (ZAP), recon-ng, padbuster
 */
function generatePrompt(test) {
  const obj = (test.objectives || "").split("\n")[0].replace(/^- /, "").trim();
  return `Thực hiện kiểm thử ${test.wstgId} (${test.name}). Mục tiêu: ${obj}. Target: {target}`;
}

export const wstgCategories = rawData.map((cat) => ({
  ...cat,
  tests: cat.tests.map((t) => ({
    ...t,
    promptTemplate: generatePrompt(t),
  })),
}));
