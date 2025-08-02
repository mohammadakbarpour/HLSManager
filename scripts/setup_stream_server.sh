#!/bin/bash

# ==============================================================================
#            HLSManager: Nginx RTMP + HLS Streaming Server Setup
# ==============================================================================
# Automated script to install and manage a secure Nginx RTMP + HLS video
# streaming server on Ubuntu, including SSL (Let's Encrypt) support.
#
# Author: Mohammad Akbarpour
# Version: 1.0 (Final)
# ==============================================================================

# --- Script Setup ---
set -euo pipefail
trap 'echo "An error occurred. Exiting..."; exit 1' ERR

# --- Configuration & Global Variables ---
NGINX_VERSION="1.26.1"
LOG_FILE="/var/log/stream_server_setup.log"
NGINX_INSTALL_PATH="/usr/local/nginx"
NGINX_CONF_PATH="${NGINX_INSTALL_PATH}/conf/nginx.conf"
NGINX_SERVICE_FILE="/etc/systemd/system/nginx.service"

# --- Colors for Output ---
C_RESET='\033[0m'
C_RED='\033[0;31m'
C_GREEN='\033[0;32m'
C_YELLOW='\033[0;33m'
C_BLUE='\033[0;34m'
C_CYAN='\033[0;36m'

# --- Helper Functions ---
info() {    echo -e "${C_BLUE}[INFO]${C_RESET} $1"; }
success() { echo -e "${C_GREEN}[SUCCESS]${C_RESET} $1"; }
warning() { echo -e "${C_YELLOW}[WARNING]${C_RESET} $1"; }
error() {   echo -e "${C_RED}[ERROR]${C_RESET} $1" >&2; }
press_enter_to_continue() { echo; read -p "Press Enter to continue..."; }

# --- Core Logic Functions ---

check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        error "This script must be run as root."
        exit 1
    fi
}

check_conflicts() {
    info "Checking for conflicting services on port 80..."
    if lsof -i :80 -sTCP:LISTEN -t >/dev/null ; then
        local conflicting_service
        conflicting_service=$(lsof -i :80 -sTCP:LISTEN -t | xargs -r ps -o comm= -p)
        warning "Found a conflicting service ('${conflicting_service}') using port 80."
        read -p "Do you want to stop and disable it to proceed? (y/n): " -n 1 -r; echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            info "Stopping and disabling ${conflicting_service}..."
            (systemctl stop "${conflicting_service}" && systemctl disable "${conflicting_service}") || warning "Could not stop ${conflicting_service}."
        else
            error "Cannot proceed with a conflicting service running. Aborting."
            exit 1
        fi
    fi
}

install_dependencies() {
    info "Updating package lists and installing dependencies..."
    apt-get update -y
    apt-get install -y build-essential libpcre3-dev libssl-dev zlib1g-dev ffmpeg at wget unzip lsof certbot
    success "Dependencies installed."
}

prepare_sources() {
    info "Preparing Nginx and RTMP module source files."
    read -p "How do you want to provide the source files? [1] Download automatically, [2] Use local files: " choice
    cd /tmp
    rm -rf nginx-* nginx-rtmp-module-*
    case $choice in
        1)
            info "Downloading Nginx v${NGINX_VERSION} and RTMP module..."
            wget -q "http://nginx.org/download/nginx-${NGINX_VERSION}.tar.gz"
            wget -q "https://github.com/arut/nginx-rtmp-module/archive/master.zip" -O rtmp.zip
            tar -zxf "nginx-${NGINX_VERSION}.tar.gz"
            unzip -q rtmp.zip
            export RTMP_MODULE_PATH="/tmp/nginx-rtmp-module-master"
            ;;
        2)
            read -e -p "Enter the full path to your Nginx tar.gz file: " NGINX_LOCAL_PATH
            read -e -p "Enter the full path to your RTMP module zip file: " RTMP_LOCAL_PATH
            if [ ! -f "$NGINX_LOCAL_PATH" ] || [ ! -f "$RTMP_LOCAL_PATH" ]; then
                error "One or both specified files do not exist. Aborting."
                exit 1
            fi
            cp "$NGINX_LOCAL_PATH" /tmp/nginx.tar.gz && cp "$RTMP_LOCAL_PATH" /tmp/rtmp.zip
            tar -zxf nginx.tar.gz && unzip -q rtmp.zip
            export RTMP_MODULE_PATH=$(find /tmp -type d -name "nginx-rtmp-module-*" -print -quit)
            ;;
        *) error "Invalid choice." && exit 1 ;;
    esac
    success "Source files are ready for compilation."
}

compile_nginx() {
    if [ ! -d "/tmp/nginx-${NGINX_VERSION}" ]; then
        error "Nginx source directory not found. Please run 'Prepare Sources' first."
        return 1
    fi
    info "Compiling Nginx from source... (This may take a few minutes)"
    cd "/tmp/nginx-${NGINX_VERSION}"
    
    # *** THE FIX IS HERE: Added --with-http_v2_module ***
    info "Configuring Nginx with RTMP and HTTP/2 modules..."
    ./configure \
        --prefix="${NGINX_INSTALL_PATH}" \
        --with-http_ssl_module \
        --with-http_v2_module \
        --add-module="${RTMP_MODULE_PATH}"

    make -j$(nproc) && make install
    success "Nginx has been compiled and installed to ${NGINX_INSTALL_PATH}."
}

manage_ssl() {
    info "The SSL Management function will now run."
    read -p "Enter the domain name for the SSL certificate: " DOMAIN_NAME
    if [ -z "$DOMAIN_NAME" ]; then error "Domain name is required."; return 1; fi
    read -p "Enter your email for renewal notices: " SSL_EMAIL
    if [ -z "$SSL_EMAIL" ]; then error "Email is required."; return 1; fi
    
    info "Stopping Nginx temporarily to obtain certificate..."
    systemctl stop nginx || true
    info "Requesting a new certificate using standalone mode..."
    certbot certonly --standalone --agree-tos --no-eff-email --preferred-challenges http -m "${SSL_EMAIL}" -d "${DOMAIN_NAME}"
    success "Certificate obtained successfully!"
    # Export the domain name so the next function can use it
    export DOMAIN_NAME_FOR_CONFIG=$DOMAIN_NAME
}

configure_and_start_nginx() {
    info "Finalizing Nginx configuration..."
    # Use the domain from SSL function if available, otherwise ask for it.
    if [ -z "${DOMAIN_NAME_FOR_CONFIG:-}" ]; then
        read -p "Enter the domain name to configure in Nginx: " DOMAIN_NAME
    else
        DOMAIN_NAME=$DOMAIN_NAME_FOR_CONFIG
        info "Using domain from SSL setup: $DOMAIN_NAME"
    fi
    if [ -z "$DOMAIN_NAME" ]; then error "Domain name is required."; return 1; fi
    
    local ssl_cert_path="/etc/letsencrypt/live/${DOMAIN_NAME}/fullchain.pem"
    if [ -f "$ssl_cert_path" ]; then
        info "SSL certificate found. Configuring Nginx for HTTPS."
        cat > "${NGINX_CONF_PATH}" <<EOF
worker_processes auto;
events { worker_connections 1024; }
rtmp { server { listen 1935; chunk_size 4096; application live { live on; record off; hls on; hls_path /var/hls; hls_fragment 3s; hls_playlist_length 60s; } } }
http {
    include mime.types; default_type application/octet-stream; sendfile on; keepalive_timeout 65;
    server { listen 80; server_name ${DOMAIN_NAME}; location /.well-known/acme-challenge/ { root /var/www/html; } location / { return 301 https://\$host\$request_uri; } }
    server {
        listen 443 ssl http2;
        server_name ${DOMAIN_NAME};
        ssl_certificate ${ssl_cert_path};
        ssl_certificate_key /etc/letsencrypt/live/${DOMAIN_NAME}/privkey.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers HIGH:!aNULL:!MD5;
        location / { root /var/www/player; index index.html; }
        location /hls { types { application/vnd.apple.mpegurl m3u8; video/mp2t ts; } root /var; add_header Cache-Control no-cache; add_header 'Access-Control-Allow-Origin' '*' always; }
    }
}
EOF
    else
        info "No SSL certificate found. Configuring Nginx for HTTP only."
        cat > "${NGINX_CONF_PATH}" <<EOF
worker_processes auto;
events { worker_connections 1024; }
rtmp { server { listen 1935; chunk_size 4096; application live { live on; record off; hls on; hls_path /var/hls; hls_fragment 3s; hls_playlist_length 60s; } } }
http {
    include mime.types; default_type application/octet-stream; sendfile on; keepalive_timeout 65;
    server {
        listen 80; server_name ${DOMAIN_NAME};
        location / { root /var/www/player; index index.html; }
        location /hls { types { application/vnd.apple.mpegurl m3u8; video/mp2t ts; } root /var; add_header Cache-Control no-cache; add_header 'Access-Control-Allow-Origin' '*' always; }
    }
}
EOF
    fi
    success "Nginx configuration file created."

    info "Creating required directories and systemd service..."
    mkdir -p /var/videos /var/www/player /var/hls /var/www/html
    cat > "${NGINX_SERVICE_FILE}" <<EOF
[Unit]
Description=Custom NGINX with RTMP
After=network.target
[Service]
Type=forking
PIDFile=${NGINX_INSTALL_PATH}/logs/nginx.pid
ExecStartPre=${NGINX_INSTALL_PATH}/sbin/nginx -t -c ${NGINX_CONF_PATH}
ExecStart=${NGINX_INSTALL_PATH}/sbin/nginx -c ${NGINX_CONF_PATH}
ExecReload=/bin/kill -s HUP \$MAINPID
ExecStop=/bin/kill -s QUIT \$MAINPID
[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload && systemctl enable nginx
    info "Restarting Nginx service..."
    systemctl restart nginx
    success "Nginx service is configured and running."
}

uninstall() {
    warning "This will stop Nginx and remove the compiled version at ${NGINX_INSTALL_PATH}."
    read -p "Are you sure? (y/n): " -n 1 -r; echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        systemctl stop nginx || true
        systemctl disable nginx || true
        rm -rf "${NGINX_INSTALL_PATH}" "${NGINX_SERVICE_FILE}"
        systemctl daemon-reload
        success "Custom Nginx has been uninstalled."
    fi
}

run_full_installation() {
    clear
    echo -e "${C_CYAN}--- Guided Server Installation Wizard ---${C_RESET}"
    info "This wizard will install and configure the entire streaming server."
    press_enter_to_continue
    
    info "Step 1 of 6: Checking for potential conflicts..."
    check_conflicts
    press_enter_to_continue

    info "Step 2 of 6: Installing system dependencies..."
    install_dependencies
    press_enter_to_continue

    info "Step 3 of 6: Preparing Nginx source code..."
    prepare_sources
    press_enter_to_continue
    
    info "Step 4 of 6: Compiling and installing Nginx..."
    compile_nginx
    press_enter_to_continue
    
    info "Step 5 of 6: Setting up SSL (Let's Encrypt)..."
    read -p "Do you want to set up a free SSL certificate now? (y/n): " -n 1 -r; echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        manage_ssl
    else
        warning "Skipping SSL installation."
    fi
    press_enter_to_continue

    info "Step 6 of 6: Finalizing Nginx configuration and starting the service..."
    configure_and_start_nginx
    
    success "🎉 Full installation complete! Your server is ready."
}

manage_server_menu() {
    while true; do
        clear
        echo -e "${C_CYAN}--- Server Management Menu ---${C_RESET}"
        echo " 1. Check Nginx Service Status"
        echo " 2. Re-configure and Restart Nginx"
        echo " 3. Install/Renew SSL Certificate"
        echo " 4. Uninstall Streaming Server"
        echo " 5. View Setup Logs"
        echo " 0. Back to Main Menu"
        echo "--------------------------"
        read -p "Enter your choice: " mgmt_choice
        case $mgmt_choice in
            1) systemctl status nginx --no-pager -l; press_enter_to_continue ;;
            2) configure_and_start_nginx; press_enter_to_continue ;;
            3) manage_ssl; info "Now run option 2 to apply the new certificate."; press_enter_to_continue ;;
            4) uninstall; press_enter_to_continue ;;
            5) tail -n 50 "${LOG_FILE}"; press_enter_to_continue ;;
            0) break ;;
            *) error "Invalid option." && sleep 1 ;;
        esac
    done
}

# --- Main Execution Block ---
main() {
    check_root
    exec &> >(tee -a "$LOG_FILE")
    echo "--- Log session started at $(date) ---"
    
    while true; do
        clear
        echo -e "${C_CYAN}"
        echo "==================================================="
        echo "      Nginx Streaming Server Setup Wizard"
        echo "==================================================="
        echo -e "${C_RESET}"
        echo "Welcome! This script automates the setup of your server."
        echo
        echo -e " 1. ${C_GREEN}Start Full Installation (Recommended for first time)${C_RESET}"
        echo -e " 2. ${C_YELLOW}Manage Existing Server${C_RESET}"
        echo -e " 0. ${C_RED}Exit${C_RESET}"
        echo
        read -p "Enter your choice [0-2]: " main_choice
        
        case $main_choice in
            1) run_full_installation; press_enter_to_continue ;;
            2) manage_server_menu ;;
            0) exit 0 ;;
            *) error "Invalid option." && sleep 2 ;;
        esac
    done
}

main
