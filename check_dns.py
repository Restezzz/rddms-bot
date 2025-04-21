import socket
import requests
import dns.resolver
import logging
import time
import sys
import ssl
import urllib3
from urllib3.exceptions import InsecureRequestWarning

# Отключаем предупреждения SSL
urllib3.disable_warnings(InsecureRequestWarning)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def check_domain_dns(domain):
    """Проверяет DNS-резолвинг домена через несколько серверов DNS."""
    logger.info(f"Проверка DNS для домена: {domain}")
    
    # Список публичных DNS серверов
    dns_servers = [
        ('1.1.1.1', 'Cloudflare'),
        ('8.8.8.8', 'Google'),
        ('9.9.9.9', 'Quad9'),
        ('208.67.222.222', 'OpenDNS'),
    ]
    
    # Стандартный DNS системы
    try:
        ip = socket.gethostbyname(domain)
        logger.info(f"✅ Системный DNS: {domain} -> {ip}")
    except socket.gaierror as e:
        logger.error(f"❌ Системный DNS: Не удалось разрешить {domain}: {e}")
    
    # Проверка через альтернативные DNS серверы
    for dns_ip, dns_name in dns_servers:
        try:
            resolver = dns.resolver.Resolver()
            resolver.nameservers = [dns_ip]
            answers = resolver.resolve(domain, 'A')
            
            for rdata in answers:
                logger.info(f"✅ DNS {dns_name} ({dns_ip}): {domain} -> {rdata}")
        except Exception as e:
            logger.error(f"❌ DNS {dns_name} ({dns_ip}): Ошибка {type(e).__name__}: {e}")

def check_direct_connection(domain, port=443):
    """Проверяет прямое TCP-соединение с сервером."""
    logger.info(f"Проверка TCP-соединения с {domain}:{port}")
    
    try:
        start_time = time.time()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(10)
        s.connect((domain, port))
        elapsed = time.time() - start_time
        logger.info(f"✅ TCP-соединение с {domain}:{port} установлено за {elapsed:.2f}с")
        s.close()
        return True
    except socket.error as e:
        logger.error(f"❌ Ошибка TCP-соединения с {domain}:{port}: {e}")
        return False

def check_ssl(domain, port=443):
    """Проверяет SSL-соединение с сервером."""
    logger.info(f"Проверка SSL-соединения с {domain}:{port}")
    
    try:
        start_time = time.time()
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        with socket.create_connection((domain, port)) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert(binary_form=True)
                elapsed = time.time() - start_time
                logger.info(f"✅ SSL-соединение с {domain}:{port} установлено за {elapsed:.2f}с")
                return True
    except (socket.error, ssl.SSLError) as e:
        logger.error(f"❌ Ошибка SSL-соединения с {domain}:{port}: {e}")
        return False

def check_api_status(url):
    """Проверяет доступность API-сервера."""
    logger.info(f"Проверка HTTP-соединения с {url}")
    
    try:
        start_time = time.time()
        response = requests.get(
            url, 
            timeout=10, 
            verify=False,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        elapsed = time.time() - start_time
        
        logger.info(f"✅ HTTP-соединение с {url}: статус {response.status_code}, время {elapsed:.2f}с")
        logger.info(f"   Заголовки ответа: {dict(response.headers)}")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка HTTP-соединения с {url}: {type(e).__name__}: {e}")
        return False

def check_ip_api_connection(ip, path="/api/v1/chat/completions"):
    """Проверяет соединение напрямую по IP с нужным Host."""
    url = f"https://{ip}{path}"
    logger.info(f"Проверка прямого соединения с IP: {url}")
    
    try:
        start_time = time.time()
        response = requests.get(
            url, 
            timeout=10, 
            verify=False,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Host": "openrouter.ai"  # Важно для обхода SNI и виртуального хостинга
            }
        )
        elapsed = time.time() - start_time
        
        logger.info(f"✅ Прямое IP-соединение с {url}: статус {response.status_code}, время {elapsed:.2f}с")
        logger.info(f"   Содержимое ответа: {response.text[:200]}...")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка прямого IP-соединения с {url}: {type(e).__name__}: {e}")
        return False

def main():
    """Проверяет соединение с серверами OpenRouter."""
    logger.info("=== Начало проверки соединения с серверами OpenRouter ===")
    
    domains = [
        "openrouter.ai",
        "api.openrouter.ai",
        "openrouterme.org"
    ]
    
    direct_ips = [
        "13.226.158.10",  # IP для openrouter.ai
        "13.226.158.23",  # Альтернативный IP
        "18.155.68.111"   # Еще альтернативный IP
    ]
    
    # Проверка DNS для каждого домена
    for domain in domains:
        check_domain_dns(domain)
        print("\n" + "-"*50 + "\n")
    
    # Проверка прямого TCP и SSL соединения
    for domain in domains:
        if check_direct_connection(domain):
            check_ssl(domain)
        print("\n" + "-"*50 + "\n")
    
    # Проверка HTTP-соединения
    urls = [
        "https://openrouter.ai/",
        "https://api.openrouter.ai/",
        "https://openrouterme.org/",
        "https://openrouter.ai/api/v1/chat/completions"
    ]
    
    for url in urls:
        check_api_status(url)
        print("\n" + "-"*50 + "\n")
    
    # Проверка соединения напрямую по IP
    for ip in direct_ips:
        check_ip_api_connection(ip)
        print("\n" + "-"*50 + "\n")
    
    logger.info("=== Завершение проверки соединения ===")
    logger.info("Для использования прямого IP соединения, добавьте IP в /etc/hosts или C:\\Windows\\System32\\drivers\\etc\\hosts:")
    for ip in direct_ips:
        logger.info(f"{ip} openrouter.ai api.openrouter.ai")

if __name__ == "__main__":
    main() 