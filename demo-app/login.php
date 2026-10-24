<?php
// Look up a user by the numeric id in ?id=, using a prepared statement.

mysqli_report(MYSQLI_REPORT_ERROR | MYSQLI_REPORT_STRICT);

header('Content-Type: text/html; charset=utf-8');

$id = filter_input(INPUT_GET, 'id', FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
if ($id === false || $id === null) {
    http_response_code(400);
    exit('Missing or invalid id.');
}

try {
    $db = new mysqli(
        getenv('DB_HOST') ?: 'localhost',
        getenv('DB_USER') ?: '',
        getenv('DB_PASS') ?: '',
        getenv('DB_NAME') ?: ''
    );
    $db->set_charset('utf8mb4');

    $stmt = $db->prepare('SELECT id, username FROM users WHERE id = ?');
    $stmt->bind_param('i', $id);
    $stmt->execute();
    $user = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    $db->close();
} catch (mysqli_sql_exception $e) {
    error_log('login.php: ' . $e->getMessage());
    http_response_code(500);
    exit('Database error.');
}

if (!$user) {
    http_response_code(404);
    exit('User not found.');
}

echo 'Hello, ' . htmlspecialchars($user['username'], ENT_QUOTES, 'UTF-8');
