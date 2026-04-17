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
  const tools = (test.tools || "").toLowerCase();

  let toolInstruction = "";
  if (tools.includes("sqlmap") || tools.includes("nosqlmap")) {
    toolInstruction = "Sử dụng sqlmap để";
  } else if (tools.includes("commix")) {
    toolInstruction = "Sử dụng commix để";
  } else if (tools.includes("tplmap")) {
    toolInstruction = "Sử dụng tplmap để";
  } else if (tools.includes("wfuzz")) {
    toolInstruction = "Sử dụng wfuzz để";
  } else if (tools.includes("padbuster") || tools.includes("poet")) {
    toolInstruction = "Sử dụng padbuster để";
  } else if (tools.includes("hydra")) {
    toolInstruction = "Sử dụng hydra để";
  } else if (tools.includes("nikto")) {
    toolInstruction = "Sử dụng nikto để";
  } else if (tools.includes("whatweb") || tools.includes("wappalyzer") || tools.includes("cmsmap")) {
    toolInstruction = "Sử dụng whatweb để";
  } else if (tools.includes("wafw00f")) {
    toolInstruction = "Sử dụng wafw00f để";
  } else if (tools.includes("testssl")) {
    toolInstruction = "Sử dụng testssl.sh để";
  } else if (tools.includes("recon-ng") || tools.includes("recon")) {
    toolInstruction = "Sử dụng recon-ng để";
  } else if (tools.includes("dnsrecon")) {
    toolInstruction = "Sử dụng dnsrecon để";
  } else if (tools.includes("nmap") || tools.includes("nessus")) {
    toolInstruction = "Sử dụng nmap để";
  } else if (tools.includes("dirb") || tools.includes("dirsearch") || tools.includes("ffuf")) {
    toolInstruction = "Sử dụng dirb để";
  } else if (tools.includes("curl") || tools.includes("netcat")) {
    toolInstruction = "Sử dụng curl để";
  } else if (tools.includes("burp") || tools.includes("zap")) {
    // ZAP headless thay thế Burp/ZAP GUI
    toolInstruction = "Sử dụng OWASP ZAP (headless) để";
  } else {
    toolInstruction = "Hãy phân tích và kiểm tra";
  }

  const obj = (test.objectives || "").split("\n")[0].replace(/^- /, "").trim();
  return `${toolInstruction} thực hiện kiểm thử ${test.wstgId} (${test.name}) trên mục tiêu {target}. Mục tiêu kiểm thử: ${obj}`;
}

export const wstgCategories = rawData.map((cat) => ({
  ...cat,
  tests: cat.tests.map((t) => ({
    ...t,
    promptTemplate: generatePrompt(t),
  })),
}));
