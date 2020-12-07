-- Drop existing tables
DROP TABLE IF EXISTS user;
DROP TABLE IF EXISTS operations;

-- Create the user table
CREATE TABLE user (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password TEXT NOT NULL
);

-- Create operations table
-- Keeps track of operations and the users that started them
CREATE TABLE operations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  requester_id INTEGER NOT NULL,
  completion TEXT NOT NULL,
  workflow_store TEXT,
  result_store TEXT,
  FOREIGN KEY (requester_id) REFERENCES user (id)
);
