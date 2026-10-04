/**
 * pm2 process definition of the Next.js web tier (apps/web, standalone build).
 *
 * Cluster mode: several Node processes share one port, so pm2 can replace
 * them one at a time while the others keep serving. deploy/web-roll.sh drives
 * that, each instance checked healthy before the next is touched.
 *
 * The processes run the standalone build under `current/web`, a folder
 * assembled once per deploy, never the checkout: a deploy builds elsewhere
 * while the live processes keep reading their own finished copy, and the
 * `current` link is switched with one atomic rename.
 *
 * The environment comes from the production environment file, read here
 * rather than inherited from whichever shell started pm2: the web server
 * reads GA_MEASUREMENT_ID, CLARITY_PROJECT_ID and the API address at request
 * time, and a build never bakes them in.
 *
 * Settings (environment of the shell that runs `pm2 start`), all optional:
 *   APP_ROOT        production root (default: /opt/tabsira)
 *   ENV_FILE        environment file (default: $APP_ROOT/shared/.env)
 *   WEB_INSTANCES   number of processes (default: 2), or `max` for one per CPU
 *   WEB_PORT        shared port nginx proxies to (default: 3000)
 *   WEB_HOST        address to bind (default: 127.0.0.1, nginx is local)
 *   LOG_DIR         where the logs go (default: /var/log/tabsira)
 */
const fs = require('node:fs');
const path = require('node:path');

const appRoot = process.env.APP_ROOT || '/opt/tabsira';
const envFile = process.env.ENV_FILE || path.join(appRoot, 'shared', '.env');
const logDir = process.env.LOG_DIR || '/var/log/tabsira';

/** KEY=VALUE lines, # comments, optional quotes; enough for our environment file. */
function readEnvFile(file) {
  const env = {};
  let text;
  try {
    text = fs.readFileSync(file, 'utf8');
  } catch {
    return env;
  }
  for (const raw of text.split('\n')) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const match = /^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/.exec(line);
    if (!match) continue;
    let value = match[2];
    const quoted = /^(['"])(.*)\1$/.exec(value);
    if (quoted) {
      value = quoted[2];
    } else {
      value = value.replace(/\s+#.*$/, '');
    }
    env[match[1]] = value;
  }
  return env;
}

const fileEnv = readEnvFile(envFile);
const setting = (key, fallback) => process.env[key] || fileEnv[key] || fallback;
const instances = setting('WEB_INSTANCES', '2');

module.exports = {
  apps: [
    {
      name: 'tabsira-web',
      cwd: path.join(appRoot, 'current', 'web', 'apps', 'web'),
      script: 'server.js',
      exec_mode: 'cluster',
      instances: instances === 'max' ? 'max' : Number(instances),
      env: {
        ...fileEnv,
        NODE_ENV: 'production',
        NEXT_TELEMETRY_DISABLED: '1',
        PORT: setting('WEB_PORT', '3000'),
        HOSTNAME: setting('WEB_HOST', '127.0.0.1'),
      },
      // A replaced process gets this long to finish its requests.
      kill_timeout: 15000,
      // How long pm2 waits for a new process to listen before giving up on it.
      listen_timeout: 30000,
      max_memory_restart: '1G',
      merge_logs: true,
      time: true,
      out_file: path.join(logDir, 'web.out.log'),
      error_file: path.join(logDir, 'web.err.log'),
    },
  ],
};
