/* Additional ARM adapter code only; the fixed 1.13d core stays unchanged.
 * Call site: recovered world_probe.so + 0x3fc0, r8 = image + WALK_PATH.
 * Arguments: r0 target y, r1 target x, r2 requested action, r3 player.
 * This matches the native mouse input's STAT_STAMINA > 0 run eligibility.
 * It prevents the adapter from restarting run while the server forces walk.
 */
.syntax unified
.arch armv7-a
.arm
.text
.global stamina_walk_path
.type stamina_walk_path,%function
stamina_walk_path:
    cmp r2, #3
    bxne r8
    push {r0-r3, r4, lr}
    mov r0, r3
    mov r1, #10
    mov r2, #0
    movw ip, #0x11a4
    movt ip, #7
    add ip, r8, ip /* STAT_VALUE (0x2ef9cc) - WALK_PATH (0x27e828) */
    blx ip
    cmp r0, #0
    pop {r0-r3, r4, lr}
    movle r2, #1
    bx r8
.size stamina_walk_path, .-stamina_walk_path
.section .note.GNU-stack,"",%progbits
