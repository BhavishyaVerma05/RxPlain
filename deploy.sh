#!/bin/bash
# Deployment script for RxPlain to Google Cloud Run

PROJECT_ID=$(gcloud config get-value project)
SERVICE_NAME="rxplain-service"
REGION="us-central1"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

# Prompt for the GROQ API key
echo "Please enter your GROQ_API_KEY (leave empty if you want to set it later via GCP console):"
read -s GROQ_API_KEY

echo "Building Docker image..."
gcloud builds submit --tag ${IMAGE}

echo "Deploying to Cloud Run..."
if [ -z "$GROQ_API_KEY" ]; then
    gcloud run deploy ${SERVICE_NAME} \
      --image ${IMAGE} \
      --region ${REGION} \
      --platform managed \
      --allow-unauthenticated \
      --port 8080
else
    gcloud run deploy ${SERVICE_NAME} \
      --image ${IMAGE} \
      --region ${REGION} \
      --platform managed \
      --allow-unauthenticated \
      --port 8080 \
      --set-env-vars GROQ_API_KEY=${GROQ_API_KEY}
fi

echo "Deployment complete! Visit the URL provided above."
