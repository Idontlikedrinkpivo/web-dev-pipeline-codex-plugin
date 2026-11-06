// Runtime adapter: one nginx master, JSON diagnostics without request data,
// and bounded graceful shutdown on the platform's TERM/INT (no Helm changes).
package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"os/signal"
	"strings"
	"sync"
	"syscall"
	"time"
)

var output sync.Mutex

func diagnostic(line string) {
	level := "error"
	for _, candidate := range []string{"debug", "info", "notice", "warn", "error", "crit", "alert", "emerg"} {
		if strings.Contains(line, "["+candidate+"]") {
			level = candidate
			break
		}
	}
	// Native nginx errors may embed full URLs, headers and arbitrary client data.
	// Keep a fixed category, never forward the raw line or command arguments.
	message := "nginx diagnostic (request details omitted)"
	for _, category := range []string{"connect() failed", "upstream timed out", "host not found", "could not be resolved", "permission denied", "invalid number", "unknown directive", "certificate verify failed", "start worker process", "signal process started", "exiting"} {
		if strings.Contains(strings.ToLower(line), strings.ToLower(category)) {
			message = category
			break
		}
	}
	record := map[string]string{"time": time.Now().UTC().Format(time.RFC3339Nano), "level": level, "logger": "nginx.error", "msg": message}
	output.Lock()
	defer output.Unlock()
	_ = json.NewEncoder(os.Stderr).Encode(record)
}

func logs(reader io.Reader, access bool, done *sync.WaitGroup) {
	defer done.Done()
	scanner := bufio.NewScanner(reader)
	scanner.Buffer(make([]byte, 4096), 1024*1024)
	for scanner.Scan() {
		raw := scanner.Bytes()
		var record map[string]interface{}
		if access && json.Unmarshal(raw, &record) == nil && record["logger"] != nil && record["msg"] != nil {
			output.Lock()
			_, _ = fmt.Fprintln(os.Stdout, string(raw))
			output.Unlock()
		} else {
			diagnostic(string(raw))
		}
	}
	if scanner.Err() != nil {
		diagnostic("log stream could not be read")
	}
}

func main() {
	if len(os.Args) < 2 {
		diagnostic("missing command")
		os.Exit(1)
	}
	command := exec.Command(os.Args[1], os.Args[2:]...)
	command.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	stdout, err := command.StdoutPipe()
	if err != nil {
		diagnostic("stdout pipe failed")
		os.Exit(1)
	}
	stderr, err := command.StderrPipe()
	if err != nil {
		diagnostic("stderr pipe failed")
		os.Exit(1)
	}
	signals := make(chan os.Signal, 4)
	signal.Notify(signals, syscall.SIGTERM, syscall.SIGINT, syscall.SIGQUIT)
	defer signal.Stop(signals)
	if command.Start() != nil {
		diagnostic("nginx start failed")
		os.Exit(1)
	}
	var readers sync.WaitGroup
	readers.Add(2)
	go logs(stdout, true, &readers)
	go logs(stderr, false, &readers)
	finished := make(chan error, 1)
	go func() { readers.Wait(); finished <- command.Wait() }()
	var deadline <-chan time.Time
	for {
		select {
		case <-signals:
			// Forward once to master, not the workers: nginx coordinates their drain.
			_ = command.Process.Signal(syscall.SIGQUIT)
			if deadline == nil {
				deadline = time.After(28 * time.Second)
			}
		case <-deadline:
			diagnostic("nginx graceful shutdown deadline exceeded")
			_ = syscall.Kill(-command.Process.Pid, syscall.SIGKILL)
			<-finished
			os.Exit(1)
		case err := <-finished:
			if err != nil {
				diagnostic("nginx exited unsuccessfully")
				os.Exit(1)
			}
			return
		}
	}
}
