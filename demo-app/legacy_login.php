<?php
// Look up a user by id using a prepared statement.
$conn = mysqli_connect("localhost", "app", "app", "demo");

$id = filter_input(INPUT_GET, 'id', FILTER_VALIDATE_INT);
if ($id === false || $id === null) {
    http_response_code(400);
    exit("Invalid id");
}

$stmt = mysqli_prepare($conn, "SELECT username FROM users WHERE id = ?");
mysqli_stmt_bind_param($stmt, "i", $id);
mysqli_stmt_execute($stmt);
$result = mysqli_stmt_get_result($stmt);

while ($row = mysqli_fetch_assoc($result)) {
    echo htmlspecialchars($row['username']) . "<br>";
}

mysqli_stmt_close($stmt);
mysqli_close($conn);
