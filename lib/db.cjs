const fs = require("fs");
const path = require("path");

function mkdirForFile(filePath) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
}

function wrapBun(db) {
  return {
    exec(sql) {
      db.run(sql);
    },
    prepare(sql) {
      const stmt = db.prepare(sql);
      return {
        run(...args) {
          stmt.run(...args);
        },
        get(...args) {
          return stmt.get(...args);
        },
        all(...args) {
          return stmt.all(...args);
        },
      };
    },
  };
}

function wrapNode(db) {
  return {
    exec(sql) {
      db.exec(sql);
    },
    prepare(sql) {
      const stmt = db.prepare(sql);
      return {
        run(...args) {
          stmt.run(...args);
        },
        get(...args) {
          return stmt.get(...args);
        },
        all(...args) {
          return stmt.all(...args);
        },
      };
    },
  };
}

function openDatabase(dbPath) {
  mkdirForFile(dbPath);

  // ONREZA runtime uses Bun
  if (typeof Bun !== "undefined") {
    const { Database } = require("bun:sqlite");
    return wrapBun(new Database(dbPath));
  }

  try {
    const { DatabaseSync } = require("node:sqlite");
    return wrapNode(new DatabaseSync(dbPath));
  } catch (err) {
    throw new Error(
      `No SQLite backend available (need Bun or Node 22+). ${err.message}`
    );
  }
}

module.exports = { openDatabase };
