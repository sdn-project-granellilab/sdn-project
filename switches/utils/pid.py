import queue

def pid(Ki,Kp,Kd,desired_consumption_perc,actual_consumption_perc,q_cap,prev_error,dt):
    traffic=actual_consumption_perc*q_cap
    req_bw=traffic/desired_consumption_perc

    error=req_bw-q_cap
    integral=Ki*error*dt
    derivative=Kd*(error-prev_error)/dt
    proportional=Kp*error
    prev_error=error
    delta=proportional+integral+derivative
    new_q=q_cap+delta
    return new_q,prev_error

def get_optimized_bw(link_cap, queues, objectives, traffic_stats, errs, dt):
    ki=0.1
    kp=0.8
    kd=0.1

    q_caps = []
    for i in range(len(queues)):
        q_caps.append(queues[i].max_rate)

    new_q_bws = []

    for i in range(len(queues)):
        q_cap,err=pid(ki,kp,kd,objectives[i],traffic_stats[i]/q_caps[i],q_caps[i],errs[i],dt)
        new_q_bws.insert(i, q_cap)
        errs[i] = err
    
    for i in range(len(new_q_bws)):
        if new_q_bws[i] <= 0:
            new_q_bws[i] = queues[i]

    cap_sum = sum(new_q_bws)
    if cap_sum > link_cap:
        for i in range(len(queues)):
            new_q_bws[i] = new_q_bws[i]*link_cap/cap_sum

    return new_q_bws, errs