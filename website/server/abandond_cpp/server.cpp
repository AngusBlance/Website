#include <fstream>
#include <iostream>
#include <netinet/in.h>
#include <sstream>
#include <sys/socket.h>
#include <unistd.h>

int main() {
  int server_fd = socket(AF_INET, SOCK_STREAM, 0);

  int opt = 1;
  setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

  sockaddr_in addr{};
  addr.sin_family = AF_INET;
  addr.sin_addr.s_addr = INADDR_ANY;
  addr.sin_port = htons(8080);

  bind(server_fd, (sockaddr *)&addr, sizeof(addr));

  listen(server_fd, 5);

  std::cout << "serving cunt on http://localhost:8080\n";

  while (true) {
    int client_fd = accept(server_fd, nullptr, nullptr);

    char buffer[4096] = {};
    read(client_fd, buffer, sizeof(buffer));

    std::ifstream file("index.html");
    std::ostringstream ss;
    ss << file.rdbuf();
    std::string body = ss.str();

    std::string response = "http/1.1 200 ok\r\n"
                           "Content-Type: text/html\r\n"
                           "Content-Length: " +
                           std::to_string(body.size()) +
                           "\r\n"
                           "\r\n" +
                           body;

    write(client_fd, response.c_str(), response.size());

    close(client_fd);
  }
  close(server_fd);
}
