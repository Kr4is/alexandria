<?php
require_once 'plugins/login-password-less.php';
// Use the "ADMINER_PASSWORD" environment variable to login to Adminer.
// The plugin will then connect to the database with an empty password.
// If the environment variable is not set, it defaults to a secure randomly generated hash to prevent unauthorized access.
$password = getenv('ADMINER_PASSWORD') ?: bin2hex(random_bytes(16));
return new AdminerLoginPasswordLess(password_hash($password, PASSWORD_DEFAULT));
