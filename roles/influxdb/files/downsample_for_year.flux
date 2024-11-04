import "bitwise"

option task = {name: "downsample_for_year", every: 30m}

calcRange = 30m
calcWindow = int(v: int(v: calcRange) / int(v: task.every) + 1)
start = time(v: int(v: int(v: now()) / int(v: task.every) - calcWindow) * int(v: task.every))
stop = time(v: int(v: int(v: now()) / int(v: task.every)) * int(v: task.every))

bor = (tables=<-, column="_value") => tables
    |> reduce(identity: {tmp: uint(v: 0),}, fn: (r, accumulator) => ({tmp: bitwise.uor(a: accumulator.tmp, b: uint(v: r._value)), }),)
    |> rename(columns: {tmp: "_value"})

from(bucket: "day")
    |> range(start: start, stop: stop)
    |> filter(fn: (r) => r["_measurement"] == "Bor")
    |> aggregateWindow(every: task.every, fn: bor, createEmpty: false)
    |> to(bucket: "year", org: "local")

from(bucket: "day")
    |> range(start: start, stop: stop)
    |> filter(fn: (r) => r["_measurement"] == "last")
    |> aggregateWindow(every: task.every, fn: last, createEmpty: false)
    |> to(bucket: "year", org: "local")

from(bucket: "day")
    |> range(start: start, stop: stop)
    |> filter(fn: (r) => r["_measurement"] == "mean")
    |> aggregateWindow(every: task.every, fn: mean, createEmpty: false)
    |> to(bucket: "year", org: "local")

from(bucket: "day")
    |> range(start: start, stop: stop)
    |> filter(fn: (r) => r["_measurement"] == "min")
    |> aggregateWindow(every: task.every, fn: min, createEmpty: false)
    |> to(bucket: "year", org: "local")

from(bucket: "day")
    |> range(start: start, stop: stop)
    |> filter(fn: (r) => r["_measurement"] == "max")
    |> aggregateWindow(every: task.every, fn: max, createEmpty: false)
    |> to(bucket: "year", org: "local")
