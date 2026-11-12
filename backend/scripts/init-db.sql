-- Runs once when the Postgres container is first created.
-- Enables pgvector in the main DB and creates a separate DB for tests.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE DATABASE twin_test;
\c twin_test
CREATE EXTENSION IF NOT EXISTS vector;
