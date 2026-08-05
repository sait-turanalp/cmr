module.exports = {
    apps: [
        {
            name: 'ucs-backend',
            cwd: './backend',
            script: './venv/bin/gunicorn',
            args: '--bind 0.0.0.0:5001 --workers 1 --threads 16 --worker-class gthread --timeout 600 --graceful-timeout 30 --max-requests 500 --max-requests-jitter 50 --preload app:app',
            interpreter: 'none',
            env: {
                FLASK_ENV: 'production',
            },
            // Lifecycle
            autorestart: true,
            watch: false,
            max_restarts: 50,
            min_uptime: '10s',
            restart_delay: 3000,
            exp_backoff_restart_delay: 1000,
            // Bellek: PM2 tum child process'leri dahil izler.
            // 16 thread + high page count islerinde 800M cok sikidir -> 4G.
            max_memory_restart: '4G',
            // Loglar
            error_file: './backend/logs/backend-error.log',
            out_file: './backend/logs/backend-out.log',
            log_date_format: 'YYYY-MM-DD HH:mm:ss',
            merge_logs: true,
            // Cokme durumunda kill timeout
            kill_timeout: 5000,
        },
        {
            name: 'ucs-frontend',
            cwd: './frontend',
            script: 'node_modules/.bin/next',
            args: 'start',
            interpreter: '/home/cmr/.nvm/versions/node/v20.19.6/bin/node',
            instances: 1,
            exec_mode: 'fork',
            env: {
                NODE_ENV: 'production',
                PORT: 3000,
                PATH: '/home/cmr/.nvm/versions/node/v20.19.6/bin:/usr/local/bin:/usr/bin:/bin',
            },
            // Lifecycle
            autorestart: true,
            watch: false,
            max_restarts: 50,
            min_uptime: '10s',
            restart_delay: 3000,
            exp_backoff_restart_delay: 1000,
            max_memory_restart: '800M',
            // Loglar
            error_file: './frontend/logs/frontend-error.log',
            out_file: './frontend/logs/frontend-out.log',
            log_date_format: 'YYYY-MM-DD HH:mm:ss',
            merge_logs: true,
            kill_timeout: 5000,
        },
    ],
}
