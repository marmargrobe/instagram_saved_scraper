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

        stage('Decrypt Env') {
            steps {
                script {
                    sh 'gpg -d .env.gpg > .env'
                }
            }
        }
        
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

        stage('Build Docker Image') {
            steps {
                script {
                    sh 'docker build -t $DOCKER_IMAGE:$DOCKER_TAG .'
                }
            }
        }

        stage('Push Docker Image') {
            steps {
                script {
                    // Login to Docker registry (Docker Hub, AWS ECR, etc.)
                    sh 'docker login -u $DOCKER_USERNAME -p $DOCKER_PASSWORD'
                    sh 'docker push $DOCKER_IMAGE:$DOCKER_TAG'
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
