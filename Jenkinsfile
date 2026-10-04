// TABSIRA continuous integration: scripted pipeline, SCM-agnostic (the job's own
// `checkout scm`, so it works with the Gitea server Jenkins clones from).
//
//   Checkout -> Prepare -> Services -> Install -> Migrations
//     -> in parallel: API tests | Vision tests | Web build and tests | Lint | Security gate | Audit
//     -> SonarQube (on main, or when RUN_SONAR is ticked) -> archive -> notify -> clean up
//
// Nothing external is written here. Addresses, names and limits come from
// jenkins/jenkins.env, may be overridden by a variable on the Jenkins job or in
// the global environment, and by a build parameter of the same name when it is
// not blank. Secrets are Jenkins credentials. docs/JENKINS_SETUP.md lists every
// key; the only credential is the SonarQube token.

// ═════════════════════════════════════════════════════════════════
//  Helpers
// ═════════════════════════════════════════════════════════════════

def readMetric(filePath) {
    if (!fileExists(filePath)) return null
    try {
        return readJSON(file: filePath)
    } catch (e) {
        echo "Skipping malformed metrics file ${filePath}: ${e.message}"
        return null
    }
}

// Run a step that comes from an optional plugin. A plugin that is not installed
// surfaces as an Error rather than an Exception, hence Throwable; the build
// carries on because nothing gates on these.
def optional(String what, Closure body) {
    try {
        body()
    } catch (Throwable t) {
        echo "${what} is unavailable (${t.message}); carrying on."
    }
}

// A badge on the build page (Badge plugin), or a plain log line without it.
def buildNote(String level, String text) {
    optional('Badge plugin') {
        if (level == 'error') {
            addErrorBadge(text: text)
        } else if (level == 'warning') {
            addWarningBadge(text: text)
        } else {
            addInfoBadge(text: text)
        }
    }
    echo "[${level}] ${text}"
}

// Resolve every key of jenkins/jenkins.env and export it to the environment of
// the build, so the stages and the scripts read one value:
//   build parameter (not blank) > Jenkins job or global variable (not blank) > the file.
def loadSettings() {
    def defaults = readProperties(file: 'jenkins/jenkins.env')
    defaults.each { key, fallback ->
        def value = params.get(key)
        if (!value) value = env.getProperty(key)
        if (!value) value = fallback
        env.setProperty(key, value ?: '')
    }
}

// Hand a Cobertura report to the Coverage plugin (trend graphs, per-file view).
// The HTML report stays published either way.
def recordCoverageReport(reportId, reportName, pattern, sourceDir) {
    if (!fileExists(pattern)) {
        echo "No coverage file at ${pattern}; nothing to record."
        return
    }
    optional('The Coverage plugin') {
        recordCoverage(
            id: reportId,
            name: reportName,
            tools: [[parser: 'COBERTURA', pattern: pattern]],
            sourceCodeRetention: 'LAST_BUILD',
            sourceDirectories: [[path: sourceDir]]
        )
    }
}

def publishHtmlReport(reportDir, reportName) {
    optional('The HTML Publisher plugin') {
        publishHTML([
            allowMissing: true,
            alwaysLinkToLastBuild: true,
            keepAll: true,
            reportDir: reportDir,
            reportFiles: 'index.html',
            reportName: reportName
        ])
    }
}

// The result of the build on Zulip. Nothing is sent unless both ZULIP_STREAM and
// ZULIP_TOPIC are set.
def sendZulipNotification(String statusLabel) {
    if (!env.ZULIP_STREAM || !env.ZULIP_TOPIC) {
        echo 'Zulip notification skipped: ZULIP_STREAM or ZULIP_TOPIC is blank.'
        return
    }
    def seconds = (currentBuild.duration / 1000) as int
    def shortCommit = (env.GIT_COMMIT ?: 'unknown').take(8)
    def lines = []
    lines << "**Build #${env.BUILD_NUMBER}: ${statusLabel}**"
    lines << ''
    lines << '| | |'
    lines << '| --- | --- |'
    lines << "| **Branch** | `${env.BRANCH_NAME ?: 'unknown'}` |"
    lines << "| **Commit** | `${shortCommit}` |"
    lines << "| **Duration** | ${(seconds / 60) as int}m${seconds % 60}s |"
    lines << ''

    def rows = []
    def api = readMetric('.ci_metrics/tests.json')
    if (api) rows << "| API tests | ${api.status}: ${api.passed} passed, ${api.failed} failed, coverage ${api.coverage}% |"
    def vision = readMetric('.ci_metrics/vision_tests.json')
    if (vision) rows << "| Vision tests | ${vision.status}: ${vision.passed} passed, ${vision.failed} failed, coverage ${vision.coverage}% |"
    def web = readMetric('.ci_metrics/web_unit_tests.json')
    if (web) rows << "| Web tests | ${web.status}${web.coverage != null ? ', coverage ' + web.coverage + '%' : ''} |"
    def format = readMetric('.ci_metrics/format.json')
    if (format) rows << "| Format | ${format.status} |"
    def gate = readMetric('.ci_metrics/security-gate.json')
    if (gate) rows << "| Security gate | ${gate.status} |"
    def audit = readMetric('.ci_metrics/audit.json')
    if (audit) rows << "| Audit (advisory) | ${audit.failures} finding(s) |"
    if (rows) {
        lines << '| Check | Result |'
        lines << '| --- | --- |'
        rows.each { lines << it }
        lines << ''
    }
    lines << "[Console](${env.BUILD_URL}console) | [Tests](${env.BUILD_URL}testReport)"

    optional('The Zulip plugin') {
        zulipSend(message: lines.join('\n'), stream: env.ZULIP_STREAM, topic: env.ZULIP_TOPIC)
    }
}

// ═════════════════════════════════════════════════════════════════
//  Parameters. A blank string means "use jenkins/jenkins.env (or the
//  Jenkins job / global variable of the same name)".
// ═════════════════════════════════════════════════════════════════

properties([
    parameters([
        booleanParam(
            name: 'RUN_SONAR',
            defaultValue: false,
            description: 'Analyse this build with SonarQube although it is not on the main branch. ' +
                'The Community Build keeps one branch, so this replaces the analysis the server shows.'
        ),
        booleanParam(
            name: 'RUN_AUDIT',
            defaultValue: true,
            description: 'Run the advisory audit (SAST, dependency advisories, hygiene). It never fails the build; findings make it unstable.'
        ),
        string(name: 'SONAR_HOST_URL', defaultValue: '', description: 'SonarQube server address. Blank: jenkins/jenkins.env.'),
        string(name: 'SONAR_PROJECT_KEY', defaultValue: '', description: 'SonarQube project key. Blank: jenkins/jenkins.env (tabsira).'),
        string(name: 'SONAR_CREDENTIALS_ID', defaultValue: '', description: 'Id of the Jenkins secret-text credential with the SonarQube token. Blank: jenkins/jenkins.env (SONAR_TOKEN).'),
        string(name: 'NODE_TOOL_NAME', defaultValue: '', description: 'Name of the NodeJS tool that provides Node 24. Blank: jenkins/jenkins.env.'),
        string(name: 'ZULIP_STREAM', defaultValue: '', description: 'Zulip stream for the result. Blank: jenkins/jenkins.env; both stream and topic blank sends nothing.'),
        string(name: 'ZULIP_TOPIC', defaultValue: '', description: 'Zulip topic for the result. Blank: jenkins/jenkins.env.'),
        string(name: 'CI_PG_IMAGE', defaultValue: '', description: 'Database image of the build (PostgreSQL 18 with PostGIS, pgvector, TimescaleDB). Blank: jenkins/jenkins.env.'),
        string(name: 'CI_REDIS_IMAGE', defaultValue: '', description: 'Redis image of the build. Blank: jenkins/jenkins.env.'),
        string(name: 'CI_PYTEST_WORKERS', defaultValue: '', description: 'Parallel pytest workers, each on its own database. Blank: jenkins/jenkins.env (0, serial).')
    ])
])

// ═════════════════════════════════════════════════════════════════
//  Pipeline
// ═════════════════════════════════════════════════════════════════

node {
    // The checked-out files. Set in the Checkout stage.
    def branch = 'unknown'

    env.ENVIRONMENT = 'development'
    // The Python apps/*/.python-version names, as uv builds it, never the agent's own python3.
    env.UV_PYTHON_PREFERENCE = 'only-managed'
    env.JENKINS_BUILD = 'true'
    env.CI = 'true'
    // No error tracking from a build (decision 24): the DSN is empty, whatever a
    // Jenkins global variable says. No analytics or telemetry from the tools either.
    env.GLITCHTIP_DSN = ''
    env.TURBO_TELEMETRY_DISABLED = '1'
    env.NEXT_TELEMETRY_DISABLED = '1'
    env.DO_NOT_TRACK = '1'

    timestamps {
        try {
            stage('Checkout') {
                // Full history is required: the security gate scans it and the
                // diff-coverage gate compares with main. Do not enable shallow clone on the job.
                def scmVars = checkout scm
                env.GIT_COMMIT = scmVars.GIT_COMMIT ?: sh(script: 'git rev-parse HEAD', returnStdout: true).trim()
                // A multibranch job sets BRANCH_NAME; a plain "pipeline from SCM" job does not.
                branch = env.BRANCH_NAME ?: (scmVars.GIT_BRANCH ?: 'unknown').replaceFirst('^origin/', '')
                env.BRANCH_NAME = branch
                loadSettings()
                currentBuild.displayName = "#${currentBuild.number} | ${branch}"
                env.NODE_HOME = tool(env.NODE_TOOL_NAME)
                def home = sh(script: 'echo "$HOME"', returnStdout: true).trim()
                env.PATH = "${env.NODE_HOME}/bin:${home}/.local/bin:${env.PATH}"
            }

            timeout(time: (env.CI_TIMEOUT_MINUTES ?: '60') as int, unit: 'MINUTES') {

                stage('Prepare') {
                    // Fail in seconds, before packages are installed for a build that cannot run.
                    sh 'bash jenkins/prepare-jenkins-deps.sh --check'
                }

                stage('Services') {
                    // Remove what a build that never reached its teardown left behind, then
                    // start this build's own PostgreSQL and Redis. The ports and the
                    // passwords are known only once they run, so they come back in .env.ci
                    // (DATABASE_URL, SYNC_DATABASE_URL, TEST_DATABASE_URL, REDIS_URL, TEST_REDIS_URL).
                    sh 'bash jenkins/ci-services.sh doctor'
                    sh 'bash jenkins/ci-services.sh sweep'
                    sh 'bash jenkins/ci-services.sh up'
                    // setProperty, not env[k]: the subscript form is rejected by the Groovy sandbox.
                    readProperties(file: '.env.ci').each { k, v -> env.setProperty(k, v) }
                    buildNote('info', "Services: database on port ${env.TABSIRA_CI_PG_PORT}, Redis on port ${env.TABSIRA_CI_REDIS_PORT}")
                }

                stage('Install') {
                    parallel(
                        'API': {
                            sh '''#!/bin/bash
                                set -euo pipefail
                                cd apps/api
                                uv sync --locked
                            '''
                        },
                        'Vision': {
                            sh '''#!/bin/bash
                                set -euo pipefail
                                cd services/vision
                                uv sync --locked
                            '''
                        },
                        'Node': {
                            sh '''#!/bin/bash
                                set -euo pipefail
                                source scripts/lib.sh
                                ensure_pnpm_version
                                pnpm install --frozen-lockfile
                            '''
                        }
                    )
                }

                stage('Migrations') {
                    // The geodata chain, then the app chain.
                    sh '''#!/bin/bash
                        set -euo pipefail
                        mkdir -p .ci_logs
                        bash scripts/migrate.sh 2>&1 | tee .ci_logs/migrations.log
                    '''
                }

                // Everything below shares nothing but the checkout, so it runs side by
                // side and the build costs its longest branch. failFast: once one branch
                // is red the build is red, and finishing the others only delays the answer.
                env.PYTEST_WORKERS = env.CI_PYTEST_WORKERS ?: '0'
                def branches = [:]

                branches['API'] = {
                    stage('API Tests') {
                        timeout(time: 45, unit: 'MINUTES') {
                            try {
                                sh '''#!/bin/bash
                                    set -euo pipefail
                                    mkdir -p .ci_logs
                                    bash scripts/test-coverage.sh 2>&1 | tee .ci_logs/tests.log
                                '''
                            } finally {
                                junit testResults: 'apps/api/coverage/junit.xml', allowEmptyResults: true
                                publishHtmlReport('apps/api/coverage/html', 'API Coverage')
                                recordCoverageReport('api-coverage', 'API Coverage', 'apps/api/coverage/coverage.xml', 'apps/api')
                                archiveArtifacts(
                                    artifacts: 'apps/api/coverage/*.xml,.ci_metrics/tests.json,.ci_logs/tests.log',
                                    allowEmptyArchive: true,
                                    fingerprint: true
                                )
                            }
                        }
                    }
                }

                branches['Vision'] = {
                    stage('Vision Tests') {
                        timeout(time: 20, unit: 'MINUTES') {
                            try {
                                sh '''#!/bin/bash
                                    set -euo pipefail
                                    mkdir -p .ci_logs
                                    bash jenkins/vision-coverage.sh 2>&1 | tee .ci_logs/vision-tests.log
                                '''
                            } finally {
                                junit testResults: 'services/vision/coverage/junit.xml', allowEmptyResults: true
                                publishHtmlReport('services/vision/coverage/html', 'Vision Coverage')
                                recordCoverageReport('vision-coverage', 'Vision Coverage', 'services/vision/coverage/coverage.xml', 'services/vision')
                                archiveArtifacts(
                                    artifacts: 'services/vision/coverage/*.xml,.ci_metrics/vision_tests.json,.ci_logs/vision-tests.log',
                                    allowEmptyArchive: true,
                                    fingerprint: true
                                )
                            }
                        }
                    }
                }

                branches['Web'] = {
                    if (fileExists('apps/web/package.json')) {
                        stage('Web Production Build') {
                            withEnv(['NODE_ENV=production']) {
                                sh '''#!/bin/bash
                                    set -euo pipefail
                                    mkdir -p .ci_logs
                                    cd apps/web
                                    pnpm build 2>&1 | tee ../../.ci_logs/web-build.log
                                '''
                            }
                        }
                        stage('Web Tests') {
                            try {
                                sh '''#!/bin/bash
                                    set -euo pipefail
                                    mkdir -p .ci_logs
                                    bash scripts/test-web-coverage.sh 2>&1 | tee .ci_logs/web-unit-tests.log
                                '''
                            } finally {
                                junit testResults: 'apps/web/coverage/junit.xml', allowEmptyResults: true
                                publishHtmlReport('apps/web/coverage', 'Web Coverage')
                                recordCoverageReport('web-coverage', 'Web Coverage', 'apps/web/coverage/cobertura-coverage.xml', 'apps/web')
                                archiveArtifacts(
                                    artifacts: 'apps/web/coverage/**/*,.ci_logs/web-*.log,.ci_metrics/web_unit_tests.json',
                                    allowEmptyArchive: true,
                                    fingerprint: true
                                )
                            }
                        }
                    } else {
                        stage('Web (skipped)') {
                            echo 'apps/web does not exist yet: no web build and no web coverage in this build.'
                            buildNote('info', 'Web skipped: apps/web does not exist yet')
                        }
                    }
                }

                branches['Lint'] = {
                    // scripts/lint.sh runs the format check first, then lint rules and
                    // types for api, vision and web, shell and Markdown.
                    stage('Lint') {
                        try {
                            sh '''#!/bin/bash
                                set -euo pipefail
                                mkdir -p .ci_logs
                                bash scripts/lint.sh 2>&1 | tee .ci_logs/lint.log
                            '''
                        } catch (e) {
                            buildNote('error', "Lint or format check failed in build ${env.BUILD_NUMBER}")
                            throw e
                        }
                    }
                }

                branches['Security'] = {
                    // Blocking: a committed secret, in the tree or anywhere in the history,
                    // and a critical advisory in a production dependency fail the build.
                    // Kept apart from the Audit below, which is advisory.
                    stage('Security Gate') {
                        try {
                            sh '''#!/bin/bash
                                set -euo pipefail
                                mkdir -p .ci_logs
                                bash scripts/security-gate.sh 2>&1 | tee .ci_logs/security-gate.log
                            '''
                        } catch (e) {
                            buildNote('error', "Security gate failed in build ${env.BUILD_NUMBER}")
                            throw e
                        }
                    }
                }

                // A parameter that was never registered (the first build after it was added) reads as null.
                if (params.RUN_AUDIT != false) {
                    branches['Audit'] = {
                        // Advisory: findings are reported and make the build unstable, never failed.
                        stage('Audit') {
                            def status = sh(
                                script: '''#!/bin/bash
                                    set -uo pipefail
                                    mkdir -p .ci_logs
                                    bash scripts/audit.sh 2>&1 | tee .ci_logs/audit.log
                                    exit "${PIPESTATUS[0]}"
                                ''',
                                returnStatus: true
                            )
                            if (status != 0) {
                                buildNote('warning', 'Audit reported findings (advisory)')
                                unstable('The audit reported findings; it is advisory and does not fail the build.')
                            }
                        }
                    }
                }

                branches.failFast = true
                parallel(branches)

                // ── SonarQube ───────────────────────────────────────────
                //
                // On the main branch, or when RUN_SONAR is ticked. It reads the coverage
                // the suites have just written; none of them runs a second time. A failed
                // quality gate, or a server that cannot be reached, makes the build
                // unstable rather than failed: red stays reserved for broken code and tests.
                // The server address is configuration: left blank, the stage says so and
                // does nothing, unless RUN_SONAR asked for it, which then fails the stage.
                if (params.RUN_SONAR || branch == env.SONAR_BRANCH) {
                    stage('SonarQube') {
                        catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE') {
                            if (!env.SONAR_HOST_URL) {
                                if (params.RUN_SONAR) {
                                    error('RUN_SONAR was ticked but SONAR_HOST_URL is blank. Set it in jenkins/jenkins.env, on the job or as a build parameter.')
                                }
                                buildNote('warning', 'SonarQube skipped: SONAR_HOST_URL is not set')
                            } else {
                                timeout(time: 20, unit: 'MINUTES') {
                                    withCredentials([string(credentialsId: env.SONAR_CREDENTIALS_ID, variable: 'SONAR_TOKEN')]) {
                                        sh '''#!/bin/bash
                                            set -euo pipefail
                                            mkdir -p .ci_logs
                                            bash jenkins/sonar-scan.sh 2>&1 | tee .ci_logs/sonarqube.log
                                        '''
                                    }
                                }
                                optional('The Badge plugin') {
                                    addBadge(
                                        icon: 'symbol-analytics plugin-ionicons-api',
                                        text: 'SonarQube analysis',
                                        link: "${env.SONAR_HOST_URL.replaceFirst('/+$', '')}/dashboard?id=${env.SONAR_PROJECT_KEY}"
                                    )
                                }
                            }
                        }
                    }
                }
            }
        } catch (org.jenkinsci.plugins.workflow.steps.FlowInterruptedException e) {
            currentBuild.result = 'ABORTED'
            throw e
        } catch (Throwable e) {
            currentBuild.result = 'FAILURE'
            buildNote('error', "Build ${env.BUILD_NUMBER} failed")
            throw e
        } finally {
            // Teardown never fails the build; `set +e` so one failing step does not
            // stop the rest. The container is removed before the workspace goes, and
            // the sweep after it collects anything an earlier build left.
            sh '''#!/bin/bash
                set +e
                if [ -f jenkins/ci-services.sh ]; then
                    bash jenkins/ci-services.sh logs
                    bash jenkins/ci-services.sh down
                    bash jenkins/ci-services.sh sweep
                fi
            '''
            archiveArtifacts(
                artifacts: '.ci_metrics/*.json,.ci_logs/*.log',
                allowEmptyArchive: true,
                fingerprint: true
            )
            sendZulipNotification(currentBuild.currentResult ?: 'SUCCESS')
            // The virtual environments and node_modules stay: they are what makes the next install fast.
            optional('The Workspace Cleanup plugin') {
                cleanWs(
                    deleteDirs: true,
                    notFailBuild: true,
                    patterns: [
                        [pattern: 'apps/api/.venv', type: 'EXCLUDE'],
                        [pattern: 'services/vision/.venv', type: 'EXCLUDE'],
                        [pattern: '**/node_modules', type: 'EXCLUDE']
                    ]
                )
            }
        }
    }
}
