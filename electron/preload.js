// electron/preload.js
const { contextBridge } = require("electron");

// Expose the base URL/port to the renderer if you want to use it
contextBridge.exposeInMainWorld("ig3", {
  baseURL: `http://127.0.0.1:${process.env.IG3_PORT || process.env.PORT || 5123}`,
});
