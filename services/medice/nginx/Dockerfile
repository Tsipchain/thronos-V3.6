FROM nginx:1.25-alpine

COPY nginx.conf /etc/nginx/nginx.conf

# Remove default config
RUN rm -f /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
