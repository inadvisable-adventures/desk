/* DeskRecorder.app's executable (TODO b9689cd, plans/desk-recorder-app.md).
 *
 * macOS ties Screen Recording / Camera / Microphone permission to the
 * app that asks, and Qt cannot ask from a Python process that has no
 * Info.plist. So this small launcher is the "app": it runs the Python
 * recorder (`python -m desk.recorder_app`) as a CHILD (not exec, so the
 * grants stay with this bundle) and requests permissions on its behalf.
 * The child gets one end of a socket pair in DESK_RECORDER_PERM_FD and
 * writes a permission name per line (camera | microphone | screen); this
 * process answers `granted`, `denied` or `restart` (Screen Recording was
 * just requested and only applies after a restart).
 *
 * Paths are baked in at build time (scripts/build_desk_recorder_app.sh):
 *   PROJECT_DIR, PYTHON_BIN, LOG_FILE.
 */
#import <AVFoundation/AVFoundation.h>
#import <CoreGraphics/CoreGraphics.h>
#include <fcntl.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <unistd.h>

extern char **environ;

static const char *request_av(AVMediaType type) {
    AVAuthorizationStatus status = [AVCaptureDevice authorizationStatusForMediaType:type];
    if (status == AVAuthorizationStatusAuthorized) return "granted";
    if (status != AVAuthorizationStatusNotDetermined) return "denied";
    __block BOOL ok = NO;
    dispatch_semaphore_t sem = dispatch_semaphore_create(0);
    [AVCaptureDevice requestAccessForMediaType:type completionHandler:^(BOOL granted) {
        ok = granted;
        dispatch_semaphore_signal(sem);
    }];
    dispatch_semaphore_wait(sem, DISPATCH_TIME_FOREVER);
    return ok ? "granted" : "denied";
}

static const char *answer(const char *name) {
    if (strcmp(name, "camera") == 0) return request_av(AVMediaTypeVideo);
    if (strcmp(name, "microphone") == 0) return request_av(AVMediaTypeAudio);
    if (strcmp(name, "screen") == 0) {
        if (CGPreflightScreenCaptureAccess()) return "granted";
        CGRequestScreenCaptureAccess();
        return "restart";
    }
    return "denied";
}

int main(int argc, char **argv) {
    @autoreleasepool {
        if (chdir(PROJECT_DIR) != 0) { perror("chdir"); return 1; }
        int log = open(LOG_FILE, O_WRONLY | O_CREAT | O_APPEND, 0644);
        int sv[2];
        if (socketpair(AF_UNIX, SOCK_STREAM, 0, sv) != 0) { perror("socketpair"); return 1; }
        fcntl(sv[0], F_SETFD, FD_CLOEXEC);  /* the child keeps only sv[1] */

        char perm_fd[32];
        snprintf(perm_fd, sizeof perm_fd, "%d", sv[1]);
        setenv("DESK_RECORDER_PERM_FD", perm_fd, 1);
        setenv("PYTHONPATH", PROJECT_DIR "/src", 1);
        setenv("PYTHONUNBUFFERED", "1", 1);

        posix_spawn_file_actions_t actions;
        posix_spawn_file_actions_init(&actions);
        if (log >= 0) {
            posix_spawn_file_actions_adddup2(&actions, log, 1);
            posix_spawn_file_actions_adddup2(&actions, log, 2);
        }
        char *child[argc + 4];
        int n = 0;
        child[n++] = PYTHON_BIN;
        child[n++] = "-m";
        child[n++] = "desk.recorder_app";
        for (int i = 1; i < argc; i++) {
            if (strncmp(argv[i], "-psn", 4) == 0) continue;  /* LaunchServices serial number */
            child[n++] = argv[i];
        }
        child[n] = NULL;
        pid_t pid;
        if (posix_spawn(&pid, PYTHON_BIN, &actions, NULL, child, environ) != 0) { perror("spawn"); return 1; }
        close(sv[1]);

        /* Answer permission requests until the child closes its end. */
        char line[128];
        size_t used = 0;
        for (;;) {
            ssize_t got = read(sv[0], line + used, sizeof(line) - 1 - used);
            if (got <= 0) break;
            used += (size_t)got;
            char *newline;
            while ((newline = memchr(line, '\n', used)) != NULL) {
                *newline = '\0';
                const char *reply = answer(line);
                dprintf(sv[0], "%s\n", reply);
                size_t rest = used - (size_t)(newline - line) - 1;
                memmove(line, newline + 1, rest);
                used = rest;
            }
            if (used >= sizeof(line) - 1) used = 0;  /* garbage: drop it */
        }
        int status = 0;
        waitpid(pid, &status, 0);
        return WIFEXITED(status) ? WEXITSTATUS(status) : 1;
    }
}
