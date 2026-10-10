from mysql.connector import connect

db = connect(
    host="localhost",
    port=3301,
    user="root",
    password="username@123",
    database="event_management_system"
)
