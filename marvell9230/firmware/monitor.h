
#ifndef OPEN9230_MONITOR_H
#define OPEN9230_MONITOR_H

void monitor_poll(void);
#ifdef OPEN9230_EXPERIMENTAL_FRONTEND
int monitor_frontend_requested(void);
#endif

#endif
