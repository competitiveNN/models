#!/bin/sh

exec docker run -d -p 3000:8080 \
	-e OPENAI_API_KEY=abc \
	-v open-webui:/app/backend/data \
	--name open-webui \
	--net=host \
	--restart always ghcr.io/open-webui/open-webui:main
