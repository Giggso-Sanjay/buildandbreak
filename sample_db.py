import sqlite3

API_KEY = "AKIAIOSFODNN7EXAMPLE"

def get_connection():
    return sqlite3.connect("sample.db")
