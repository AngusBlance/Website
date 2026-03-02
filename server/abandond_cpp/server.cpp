#include <fstream>
#include <iostream>
#include <netinet/in.h>
#include <sstream>
#include <string>
#include <sys/socket.h>
#include <unistd.h>

class WebServer {
private:
  int server_fd;
  int port;
  struct sockaddr_in address;

public:
  // Constructor: Sets up the socket
  WebServer(int p) : port(p) {
    server_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (server_fd < 0) {
      throw std::runtime_error("Failed to create socket");
    }

    address.sin_family = AF_INET;
    address.sin_addr.s_addr = INADDR_ANY;
    address.sin_port = htons(port);

    if (bind(server_fd, (struct sockaddr *)&address, sizeof(address)) < 0) {
      throw std::runtime_error("Failed to bind to port");
    }
  }

  // Destructor: Ensures the socket is closed
  ~WebServer() {
    if (server_fd >= 0) {
      close(server_fd);
      std::cout << "Server socket closed." << std::endl;
    }
  }

  void start() {
    listen(server_fd, 10);
    std::cout << "Server listening on http://localhost:" << port << std::endl;

    while (true) {
      int new_socket = accept(server_fd, nullptr, nullptr);
      if (new_socket >= 0) {
        handleRequest(new_socket);
      }
    }
  }

private:
  void handleRequest(int client_socket) {
    char buffer[2048] = {0};
    read(client_socket, buffer, 2048);
    std::string request(buffer);

    // Extract path from "GET /stylesheets/style.css HTTP/1.1"
    size_t first_space = request.find(" ");
    size_t second_space = request.find(" ", first_space + 1);
    if (first_space == std::string::npos || second_space == std::string::npos) {
      close(client_socket);
      return;
    }

    std::string path =
        request.substr(first_space + 1, second_space - first_space - 1);
    if (path == "/")
      path = "/index.html";

    // Combine ".." with "/stylesheets/style.css" -> "../stylesheets/style.css"
    std::string full_path = ".." + path;

    // Open in BINARY mode to support more than just text
    std::ifstream file(full_path, std::ios::binary);

    if (file.is_open()) {
      // Efficiently read file into a string
      std::string body((std::istreambuf_iterator<char>(file)),
                       std::istreambuf_iterator<char>());

      // Content-Type Mapping
      std::string contentType = "text/plain";
      if (path.find(".html") != std::string::npos)
        contentType = "text/html";
      else if (path.find(".css") != std::string::npos)
        contentType = "text/css";
      else if (path.find(".js") != std::string::npos)
        contentType = "application/javascript";
      else if (path.find(".png") != std::string::npos)
        contentType = "image/png";

      std::string header = "HTTP/1.1 200 OK\r\n"
                           "Content-Type: " +
                           contentType +
                           "\r\n"
                           "Content-Length: " +
                           std::to_string(body.size()) +
                           "\r\n"
                           "Connection: close\r\n\r\n";

      send(client_socket, header.c_str(), header.size(), 0);
      send(client_socket, body.c_str(), body.size(), 0);
    } else {
      std::string notFound = "HTTP/1.1 404 Not Found\r\nContent-Length: "
                             "0\r\nConnection: close\r\n\r\n";
      send(client_socket, notFound.c_str(), notFound.size(), 0);
    }
    close(client_socket);
  }
};

int main() {
  try {
    WebServer server(8080);
    server.start();
  } catch (const std::exception &e) {
    std::cerr << "Error: " << e.what() << std::endl;
    return 1;
  }
  return 0;
}
