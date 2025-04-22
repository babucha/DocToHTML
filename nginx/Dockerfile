FROM nginx:alpine

COPY nginx/nginx.conf /etc/nginx/conf.d/default.conf

COPY docx_converter/static /app/static

RUN mkdir -p /app/media

