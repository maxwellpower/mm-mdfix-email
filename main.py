# Mattermost Message Formatter - Email Markdown Removal

# Copyright (c) 2023 Maxwell Power
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without
# restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom
# the Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE
# AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

# -*- coding: utf-8 -*-

VERSION = "1.1.0"

import os
import re
import psycopg2
import logging

# Setup basic logging to stdout
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Check if the environment variables are set
if not (os.environ.get('DB_HOST') or os.environ.get('DB_USER') or os.environ.get('DB_PASSWORD') or os.environ.get('DB_NAME')):
    logging.error("Environment Variables are NOT set!")
    exit()

# Fetch database connection details from environment variables
DB_HOST = os.environ.get('DB_HOST')
DB_PORT = os.environ.get('DB_PORT', 5432)
DB_USER = os.environ.get('DB_USER')
DB_PASSWORD = os.environ.get('DB_PASSWORD')
DB_NAME = os.environ.get('DB_NAME')
CHANNEL_ID = os.environ.get('CHANNEL_ID', None)
COMMIT_MODE = os.environ.get('COMMIT_MODE', 'false').lower() == 'true'
DEBUG = os.environ.get('DEBUG', 'false').lower() == 'true'

logging.info(f"Starting mm-mdfix-email v{VERSION} ...")
if COMMIT_MODE:
    logging.info("COMMIT MODE: ENABLED")
else:
    logging.info("COMMIT MODE: DISABLED")

# Connect to the PostgreSQL database
try:
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME
    )
except psycopg2.OperationalError as e:
    logging.error(f"Failed to connect to the database: {e}")
    exit()

cursor = conn.cursor()
update_cursor = conn.cursor()

if cursor:
    logging.debug(f"Connecting to {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME} ...")
    logging.info(f"Successfully connected to database {DB_NAME}")

# Fetch messages from the posts table, optionally filtered by channelid, and where deleteat is set to 0 or NULL
if CHANNEL_ID:
    if DEBUG:
        cursor.execute("SELECT count(id) FROM posts WHERE channelid = %s AND (deleteat = 0) AND TRIM(message) <> ''", (CHANNEL_ID,))
        debugCount = cursor.fetchone()[0]
    cursor.execute(
        "SELECT id, message FROM posts WHERE channelid = %s AND (deleteat = 0) AND TRIM(message) <> ''", (CHANNEL_ID,))
else:
    if DEBUG:
        cursor.execute("SELECT count(id) FROM posts WHERE deleteat = 0 AND TRIM(message) <> ''")
        debugCount = cursor.fetchone()[0]
    cursor.execute(
        "SELECT id, message FROM posts WHERE deleteat = 0 AND TRIM(message) <> ''")

# Output the number of rows found
if DEBUG:
    logging.debug(f"Found {debugCount} posts to process!")

# Function to remove Markdown from email addresses
def remove_markdown_from_emails(content):
    email_pattern = r'\[([^\]]+)\]\(mailto:([^\)]+)\)'
    return re.sub(email_pattern, r'\2', content)

# Function to process each match
def format_code_blocks(message):
    pattern = r'```((?:.|\n)*)```'

    def process_match(match):
        content = match.group(1)
        content = remove_markdown_from_emails(content)
        return f"```{content}```"

    return re.sub(pattern, process_match, message)

# Process and update each message
logging.info(f"Processing posts ...")

for record in cursor:
    post_id, message = record
    if '```' in message:
        logging.debug(f"Found a message with a code block (Post ID: {post_id})")
        formatted_message = format_code_blocks(message)
        if message != formatted_message:
            logging.info(f"Processing Post ID: {post_id}")
            logging.info("Original Message:\n-----------------\n" + message)
            logging.info("Formatted Message:\n------------------\n" + formatted_message)
            if COMMIT_MODE:
                try:
                    update_cursor.execute(
                        "UPDATE posts SET message = %s WHERE id = %s", (formatted_message, post_id))
                    conn.commit()  # Commit the update

                    # Fetch the updated message from the database to verify
                    verification_cursor = conn.cursor()
                    verification_cursor.execute(
                        "SELECT message FROM posts WHERE id = %s", (post_id,))
                    updated_message = verification_cursor.fetchone()[0]
                    verification_cursor.close()

                    # Compare the updated message with the formatted message
                    if updated_message.strip() == formatted_message.strip():
                        logging.info(f"Post ID: {post_id} - Update verified successfully.")
                    else:
                        logging.error(f"Post ID: {post_id} - Update verification failed. The message in the database does not match the expected formatted message.")

                except Exception as e:
                    logging.error(f"Error while committing Post ID: {post_id}. Error: {e}")
                    conn.rollback()  # Rollback in case of error
        else:
            logging.debug(f"No formatting changes required for Post ID: {post_id}")

# Commit the changes, rollback if not in commit mode
if COMMIT_MODE:
    logging.info("Changes committed to the database.")
else:
    logging.warning("No changes were committed to the database! Run in COMMIT_MODE to apply changes.")

# Close the cursors and the connection
cursor.close()
update_cursor.close
