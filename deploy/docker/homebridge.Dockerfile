FROM node:24-bookworm-slim

ENV NODE_ENV=production

RUN npm install -g homebridge@2.3.0 homebridge-config-ui-x@5.27.0 \
    && npm cache clean --force \
    && mkdir -p /homebridge

WORKDIR /homebridge

CMD ["homebridge", "-I", "-U", "/homebridge"]
