pipeline {
    agent any
    
    parameters {
        string(
            name: 'AMGID', 
            defaultValue: 'AMG00136', 
            description: 'Enter AMGID to validate (e.g., AMG00136, AMG27125)',
            trim: true
        )
        
        choice(
            name: 'VALIDATION_TYPE',
            choices: ['both', 'cdn-only', 'mediaconnect-only'],
            description: 'Select what to validate:\n• both - Validate CDN streams and MediaConnect flows\n• cdn-only - Validate CDN streams only\n• mediaconnect-only - Validate MediaConnect flows only'
        )
        
        string(
            name: 'TEST_DURATION',
            defaultValue: '120',
            description: 'CDN test duration in seconds (default: 120)',
            trim: true
        )
    }
    
    environment {
        AWS_DEFAULT_REGION = "ap-south-1"
        SECRET_NAME = "bxp_token"
        SECRET_REGION = "ap-south-1"
        VALIDATION_MODE = "${params.VALIDATION_TYPE}"
        PATH = "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:${env.PATH}"
    }
    
    stages {
        stage('📦 Checkout Code') {
            steps {
                script {
                    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                    echo "  📦 CHECKOUT: Cloning repository from GitHub"
                    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                }
                checkout scm
                sh 'ls -la'
            }
        }
        
        stage('🔧 Setup Environment') {
            steps {
                script {
                    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                    echo "  🔧 SETUP: Installing Python dependencies"
                    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                }
                sh '''
                    echo "Creating Python virtual environment..."
                    python3 -m venv venv
                    
                    echo "Activating virtual environment..."
                    . venv/bin/activate
                    
                    echo "Upgrading pip..."
                    pip install --upgrade pip --quiet
                    
                    echo "Installing requirements..."
                    pip install -r requirements.txt --quiet
                    
                    echo "✓ Environment setup complete!"
                '''
            }
        }
        
        stage('🔐 Verify AWS Access') {
            steps {
                script {
                    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                    echo "  🔐 AWS VERIFICATION: Testing credentials and secret access"
                    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                }
                sh '''
                    . venv/bin/activate
                    
                    echo "Testing AWS credentials..."
                    aws sts get-caller-identity
                    
                    echo ""
                    echo "Running AWS configuration test..."
                    python3 test_secrets.py
                '''
            }
        }
        
        stage('🚀 Run Validation') {
            steps {
                script {
                    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                    echo "  🚀 VALIDATION: Running CDN & MediaConnect validation"
                    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                    echo ""
                    echo "  📋 Configuration:"
                    echo "     • AMGID: ${params.AMGID}"
                    echo "     • Validation Type: ${params.VALIDATION_TYPE}"
                    echo "     • Test Duration: ${params.TEST_DURATION} seconds"
                    echo "     • Secret: ${env.SECRET_NAME} (${env.SECRET_REGION})"
                    echo ""
                    
                    // Determine validation flags
                    def validationFlag = ''
                    def validationDescription = ''
                    
                    if (params.VALIDATION_TYPE == 'cdn-only') {
                        validationFlag = '--cdn'
                        validationDescription = 'CDN Streams Only'
                    } else if (params.VALIDATION_TYPE == 'mediaconnect-only') {
                        validationFlag = '--mc'
                        validationDescription = 'MediaConnect Flows Only'
                    } else {
                        validationFlag = ''
                        validationDescription = 'Both CDN & MediaConnect'
                    }
                    
                    echo "  🎯 Validating: ${validationDescription}"
                    echo ""
                    
                    sh """
                        . venv/bin/activate
                        
                        python3 main.py ${params.AMGID} ${validationFlag} \
                            --test-duration ${params.TEST_DURATION} \
                            --secret-name ${env.SECRET_NAME} \
                            --secret-region ${env.SECRET_REGION}
                    """
                }
            }
        }
        
        stage('📊 Archive Reports') {
            steps {
                script {
                    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                    echo "  📊 ARCHIVING: Saving CSV reports"
                    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                }
                
                // List generated reports
                sh 'ls -lh Reports/'
                
                // Archive artifacts
                archiveArtifacts artifacts: 'Reports/*.csv', 
                                 fingerprint: true,
                                 allowEmptyArchive: false
                
                echo "✓ Reports archived successfully!"
            }
        }
    }
    
    post {
        always {
            script {
                echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                echo "  🧹 CLEANUP: Removing workspace files"
                echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            }
            cleanWs()
        }
        
        success {
            script {
                // Get list of generated reports
                def cdnReport = sh(
                    script: "ls Reports/CDN_Test_Report_*.csv 2>/dev/null || echo 'None'",
                    returnStdout: true
                ).trim()
                
                def mcReport = sh(
                    script: "ls Reports/MediaConnect_Report_*.csv 2>/dev/null || echo 'None'",
                    returnStdout: true
                ).trim()
                
                echo ""
                echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                echo "  ✅ VALIDATION COMPLETED SUCCESSFULLY!"
                echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                echo ""
                echo "  📋 Summary:"
                echo "     • AMGID: ${params.AMGID}"
                echo "     • Type: ${params.VALIDATION_TYPE}"
                echo "     • Duration: ${currentBuild.durationString.replace(' and counting', '')}"
                echo ""
                echo "  📄 Reports Generated:"
                if (cdnReport != 'None') {
                    echo "     ✓ CDN Test Report"
                }
                if (mcReport != 'None') {
                    echo "     ✓ MediaConnect Report"
                }
                echo ""
                echo "  📥 Download reports from Build Artifacts section"
                echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                
                // Set build description with download link
                currentBuild.description = """
                    <div style="font-family: monospace;">
                        <h3>✅ Validation Complete</h3>
                        <table style="border-collapse: collapse; margin-top: 10px;">
                            <tr>
                                <td style="padding: 5px; font-weight: bold;">AMGID:</td>
                                <td style="padding: 5px;">${params.AMGID}</td>
                            </tr>
                            <tr>
                                <td style="padding: 5px; font-weight: bold;">Type:</td>
                                <td style="padding: 5px;">${params.VALIDATION_TYPE}</td>
                            </tr>
                            <tr>
                                <td style="padding: 5px; font-weight: bold;">Duration:</td>
                                <td style="padding: 5px;">${currentBuild.durationString.replace(' and counting', '')}</td>
                            </tr>
                        </table>
                        <p style="margin-top: 15px;">
                            <a href="${env.BUILD_URL}artifact/Reports/*zip*/Reports.zip" style="background-color: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 4px;">
                                📦 Download All Reports (ZIP)
                            </a>
                        </p>
                    </div>
                """
            }
        }
        
        failure {
            script {
                echo ""
                echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                echo "  ❌ VALIDATION FAILED"
                echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                echo ""
                echo "  Please check the console output above for error details."
                echo "  Common issues:"
                echo "    • AWS credentials not configured"
                echo "    • Secret 'bxp_token' not found in Secrets Manager"
                echo "    • Network connectivity issues"
                echo "    • Invalid AMGID"
                echo ""
                echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                
                currentBuild.description = """
                    <div style="font-family: monospace; color: #d32f2f;">
                        <h3>❌ Validation Failed</h3>
                        <p>Check console output for details.</p>
                        <p><a href="${env.BUILD_URL}console">View Console Output</a></p>
                    </div>
                """
            }
        }
    }
}

