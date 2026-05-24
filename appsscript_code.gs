/**
 * TG Direct Downloader — Google Apps Script
 *
 * Sheet columns: unique_id | file_name | file_size | channel_msg_id | chat_id | message_id | big | added_at | mime_type
 */

const SHEET_NAME = "Files";

function getOrCreateSheet() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(SHEET_NAME);
    sheet.appendRow([
      "unique_id", "file_name", "file_size",
      "channel_msg_id", "chat_id", "message_id",
      "big", "added_at", "mime_type"
    ]);
    sheet.getRange(1, 1, 1, 9).setFontWeight("bold").setBackground("#4a86e8").setFontColor("#ffffff");
    sheet.setFrozenRows(1);
  }
  return sheet;
}

function doPost(e) {
  try {
    const data   = JSON.parse(e.postData.contents);
    const action = data.action;
    if      (action === "append")  return handleAppend(data);
    else if (action === "getAll")  return handleGetAll();
    else if (action === "getOne")  return handleGetOne(data);
    else if (action === "update")  return handleUpdate(data);
    else return jsonResponse({ status: "error", message: "Unknown action: " + action });
  } catch (err) {
    return jsonResponse({ status: "error", message: err.toString() });
  }
}

function doGet(e) {
  const action = (e.parameter && e.parameter.action) || "getAll";
  if (action === "getAll") return handleGetAll();
  if (action === "getOne") return handleGetOne(e.parameter);
  return jsonResponse({ status: "ok", message: "TG Direct Downloader Sheet API" });
}

function handleAppend(data) {
  const sheet = getOrCreateSheet();
  sheet.appendRow([
    data.unique_id      || "",
    data.file_name      || "",
    data.file_size      || "0",
    data.channel_msg_id || "",
    data.chat_id        || "",
    data.message_id     || "",
    data.big            || "FALSE",
    data.added_at       || new Date().toISOString(),
    data.mime_type      || ""
  ]);
  return jsonResponse({ status: "ok", action: "append" });
}

function handleGetAll() {
  const sheet = getOrCreateSheet();
  const rows  = sheet.getDataRange().getValues();
  if (rows.length <= 1) return jsonResponse({ status: "ok", rows: [] });

  const headers = rows[0];
  const result  = [];
  for (let i = 1; i < rows.length; i++) {
    const row = rows[i];
    if (!row[0]) continue;
    const obj = {};
    headers.forEach((h, idx) => { obj[h] = String(row[idx] !== undefined ? row[idx] : ""); });
    result.push(obj);
  }
  return jsonResponse({ status: "ok", rows: result });
}

// NEW: fetch single row by unique_id — used for lazy cache reload after restart
function handleGetOne(data) {
  const uid = data.unique_id;
  if (!uid) return jsonResponse({ status: "error", message: "unique_id required" });

  const sheet   = getOrCreateSheet();
  const allData = sheet.getDataRange().getValues();
  const headers = allData[0];

  for (let i = 1; i < allData.length; i++) {
    if (String(allData[i][0]) === String(uid)) {
      const obj = {};
      headers.forEach((h, idx) => { obj[h] = String(allData[i][idx] !== undefined ? allData[i][idx] : ""); });
      return jsonResponse({ status: "ok", row: obj });
    }
  }
  return jsonResponse({ status: "not_found", row: null });
}

function handleUpdate(data) {
  const sheet = getOrCreateSheet();
  const uid   = data.unique_id;
  if (!uid) return jsonResponse({ status: "error", message: "unique_id required" });

  const allData = sheet.getDataRange().getValues();
  for (let i = 1; i < allData.length; i++) {
    if (String(allData[i][0]) === String(uid)) {
      if (data.channel_msg_id !== undefined) {
        sheet.getRange(i + 1, 4).setValue(data.channel_msg_id);
      }
      return jsonResponse({ status: "ok", action: "update", row: i + 1 });
    }
  }
  return jsonResponse({ status: "not_found", unique_id: uid });
}

function jsonResponse(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
