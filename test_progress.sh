#!/bin/bash

echo "=== Testing Progress Updates ==="
echo ""

# Submit task
echo "Submitting analysis task..."
RESPONSE=$(curl -s -X POST http://localhost:8000/analyze/async \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://www.shopify.com", "deep_info": false}')

TASK_ID=$(echo "$RESPONSE" | jq -r '.task_id')
echo "Task ID: $TASK_ID"
echo ""

# Poll status every 1.5 seconds for 30 seconds
for i in {1..20}; do
  echo "Poll #$i at $(date '+%H:%M:%S'):"
  STATUS_RESPONSE=$(curl -s http://localhost:8000/analyze/status/$TASK_ID)
  echo "$STATUS_RESPONSE" | jq '{status, message, progress}'

  STATUS=$(echo "$STATUS_RESPONSE" | jq -r '.status')
  if [ "$STATUS" = "SUCCESS" ] || [ "$STATUS" = "FAILURE" ]; then
    echo ""
    echo "Task completed with status: $STATUS"
    break
  fi

  echo ""
  sleep 1.5
done
