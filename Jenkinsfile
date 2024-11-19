pipeline {
    agent any

    environment {
        VENV_DIR = '.venv'
    }

    stages {
        stage('Clone') {
            steps {
                // Check out the code from the source repository
                checkout scm
            }
        }
        
        stage('Setup Python') {
            steps {
                script {
                    // Install Python virtual environment and dependencies
                    sh 'python3 -m venv $VENV_DIR'
                    sh './$VENV_DIR/bin/pip install --upgrade pip'
                    sh './$VENV_DIR/bin/pip install -r requirements.txt'
                }
            }
        }

        // stage('Run Tests') {
        //     steps {
        //         script {
        //             // Run tests using pytest or your testing framework of choice
        //             sh './$VENV_DIR/bin/pytest'
        //         }
        //     }
        // }
        
        // stage('Static Analysis') {
        //     steps {
        //         script {
        //             // Run linting (optional, for code quality)
        //             sh './$VENV_DIR/bin/flake8 .'
        //         }
        //     }
        // }

        stage('Build') {
            steps {
                script {
                    // Build stage for packaging if needed (optional)
                    echo 'Building project...'
                }
            }
        }
    }

    post {
        always {
            // Clean up the virtual environment
            deleteDir()
        }
        success {
            echo 'Build was successful!'
        }
        failure {
            echo 'Build failed.'
        }
    }
}
