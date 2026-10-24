package main

import (
	"fmt"
	"net"
	"net/http"
	"os/exec"
)

func ping(w http.ResponseWriter, r *http.Request) {
	ip := net.ParseIP(r.URL.Query().Get("host"))
	if ip == nil {
		http.Error(w, "host must be an IP address", http.StatusBadRequest)
		return
	}
	out, err := exec.Command("ping", "-c", "1", ip.String()).CombinedOutput()
	if err != nil {
		http.Error(w, "ping failed", http.StatusBadGateway)
		return
	}
	fmt.Fprint(w, string(out))
}

func main() {
	http.HandleFunc("/ping", ping)
	http.ListenAndServe(":8080", nil)
}
