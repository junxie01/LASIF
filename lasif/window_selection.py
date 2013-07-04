#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Window selection algorithm.

This module aims to provide a window selection algorithm suitable for
calculating phase misfits between two seismic waveforms.

The main function is the plot_windows() function. The selection process is a
multi-stage process. Initially all time steps are considered to be valid in
the sense as being suitable for window selection. Then a number of selectors
is applied, progressively excluding more and more time steps.

Unscientific description of the employed algorithm. Some figures would be
needed to really explain the reasoning behind it and the wording should be
clearer:

1. All time steps before the theoretical first arrival (calculated with
   TauP) are set to invalid.
2. A local extrema finding algorithm is employed, finding all local troughs
   and peaks for data and synthetics.
3. A kind of instantaneous peak-to-peak and trough-to-trough distance and a
   mix of both is calculated for data and synthetics.
3. At each time step, the relative difference between those metrics for data
   and synthetics is calculated. Every time step where the maximum for
   each of the three previously described metrics exceeds 1.0 is set to
   invalid. This keeps the difference in "wiggliness" between data and
   synthetics at a reasonable level.
4. Now the peaks and troughs for data and synthetics are directly compared.
   For every suitable window, it should be possible to map every peak in the
   data to one in the synthetics. Time intervals where this is not possible
   are set to invalid.
5. All of the above now results in a list of potential windows that will
   have to pass some further selection tests:

   1. The minimum length for each window will be restricted to one dominant
      period.
   2. The "energy" of data and synthetics in one window should not differ by
      more than one order of magnitude. The "energy" used here is simply the
      sum of all squared values in each window. This is reasonable for velocity
      seismograms. All windows not fulfilling this will be rejected.
   3. The maxmimum amplitude of the data in each window must be
      significantly above the noise level. The noise level is determined by
      taking the maximum amplitude before the first arrival.


:copyright:
    Lion Krischer (krischer@geophysik.uni-muenchen.de), 2013

:license:
    GNU General Public License, Version 3
    (http://www.gnu.org/copyleft/gpl.html)
"""
import numpy as np
from obspy.core.util import geodetics
from obspy.taup import getTravelTimes


def find_local_extrema(data, start_index=0):
    """
    A simplistic 1D local peak (and trough) detection algorithm.

    It is only useful for smooth data and will find ALL local extrema. A local
    minimum is defined as having larger values as its immediate neighbours. A
    local maximum is consequently defined as having smaller values in its
    immediate vicinity.

    Will also find local extrema at the domain borders.

    :param data: A 1D array over which the search will be performed.
    :type data: np.ndarray
    :param start_index: The minimum index at which extrema will be detected.
    :return: Returns a tuple with three arrays:
        * [0]: The indices of all found peaks
        * [1]: The indices of all found troughs
        * [2]: The indices of all found extreme points (peaks and troughs)

    >>> data = np.array([0, 1, 2, 1, 0, 1, 2, 1])
    >>> peaks, troughs, extrema = find_local_extrema(data)
    >>> peaks
    array([2, 6])
    >>> troughs
    array([0, 4, 7])
    >>> extrema
    array([0, 2, 4, 6, 7])
    """
    # Detect peaks.
    peaks = np.r_[True, data[1:] > data[:-1]] & \
        np.r_[data[:-1] > data[1:], True]
    peaks = np.where(peaks)[0]
    peaks = peaks[np.where(peaks >= start_index)[0]]

    troughs = np.r_[True, data[1:] < data[:-1]] & \
        np.r_[data[:-1] < data[1:], True]
    troughs = np.where(troughs)[0]
    troughs = troughs[np.where(troughs >= start_index)[0]]

    # Now create a merged version.
    if np.intersect1d(peaks, troughs, assume_unique=True):
        msg = "Error. Peak and troughs should not be identical! Something " \
            "went wrong. Please fix it or contact the developers."
        raise Exception(msg)
    extrema = np.concatenate([peaks, troughs])
    extrema.sort()

    return peaks, troughs, extrema


def complete_index_distance(indices, final_length):
    """
    Calculates the "instantaneous distance" between the two closest indices.

    These indices usually denote peaks or troughs in the data. So this
    function essentially shows, at any point in an array,
    the distance between the two closests peaks/troughs.

    :param indices: The indices where something interesting happens.
    :type indices: np.array
    :param final_length: The actual length of the array you are insterested
        in. Needed in case the indices do not contain the last element.
    :type final_length: int

    :return: A new array of length 'final_length'. Each point contains the
        distance between the two closest indices of interest. If actually at
         an index, it will return the mean distance to the left and right
         next neighbours.

    >>> data = np.array([2, 6, 7])
    >>> complete_index_distance(data, 10)
    array([ 3. ,  3. ,  3.5,  4. ,  4. ,  4. ,  2.5,  2. ,  3. ,  3. ])

    The handling of indices directly at the array borders follows the usual
    rules. Interpretation of this is more difficult.

    >>> data = np.array([0, 2, 4, 5])
    >>> complete_index_distance(data, 6)
    array([ 1.5,  2. ,  2. ,  2. ,  1.5,  1. ])
    """
    interpeak_distance = np.empty(final_length)

    # Left border handling. Degrades gracefully in case there is no border.
    interpeak_distance[:indices[0]] = indices[0] + 1
    # Now handle the middle parts.
    for _i in xrange(len(indices) - 1):
        left_idx = indices[_i]
        right_idx = indices[_i + 1]
        right_distance = right_idx - left_idx
        if _i == 0:
            left_distance = left_idx + 1
        else:
            left_distance = left_idx - indices[_i - 1]
        interpeak_distance[left_idx: right_idx + 1] = right_distance
        # The points at the actual indices should be the average of the
        # length before and after.
        interpeak_distance[left_idx] = (right_distance + left_distance) * 0.5
    # Right border handling.
    final_distance = final_length - indices[-1]
    interpeak_distance[indices[-1] + 1:] = final_distance
    interpeak_distance[indices[-1]] = (final_distance +
        (indices[-1] - indices[-2])) * 0.5
    return interpeak_distance


def find_ones(data):
    """
    Simple generator yielding the first and last index of any
    continuous chunk of ones in the passed data array.

    :param data: The array over which the serach will be performed.
    :type data: np.ndarray
    :returns: A generator yieling tuples of indices delimiting continuous
        areas of ones in data.

    >>> data = [0, 1, 7, 1, 1, 1, 2, 1]
    >>> for idx_min, idx_max in find_ones(data): print idx_min, idx_max
    1 1
    3 5
    7 7
    """
    start_index = None
    idx = -1
    for value in data:
        idx += 1
        if value == 1:
            if start_index is None:
                start_index = idx
                continue
            continue
        else:
            if start_index is None:
                continue
            yield start_index, idx - 1
            start_index = None
    if start_index:
        yield start_index, idx


def find_closest(ref_array, target):
    """
    For every value in target, find the index of ref_array to which
    the value is closest.

    from http://stackoverflow.com/a/8929827/1657047

    :param ref_array: The reference array. Must be sorted!
    :type ref_array: np.ndarray
    :param target: The target array.
    :type target: np.ndarray

    >>> ref_array = np.arange(0, 20.)
    >>> target = np.array([-2, 100., 2., 2.4, 2.5, 2.6])
    >>> find_closest(ref_array, target)
    array([ 0, 19,  2,  2,  3,  3])
    """
    # A must be sorted
    idx = ref_array.searchsorted(target)
    idx = np.clip(idx, 1, len(ref_array) - 1)
    left = ref_array[idx - 1]
    right = ref_array[idx]
    idx -= target - left < right - target
    return idx


def skip_finder(d, s):
    """
    Skip finder.

    This is where the magic happens. The generator takes two arrays
    containing indices of peak or troughs (could also be other things). One
    array usually contains the extramal points of the data, the other the
    extremal points of the synthetics.

    The algorithm takes care to only yield windows that have no tremendous
    difference in cycles.

    It yields tuples of indices for each window which it deems acceptable.

    :param d: An array of peak/trough/other indices
    :type d: np.ndarray
    :param s: An array of peak/trough/other indices
    :type s: np.ndarray
    :returns: A generator yielding tuples with minimal and maximal indices
        of window it deems acceptable.
    """
    for min_idx, max_idx in find_ones(np.diff(find_closest(d, s))):
        left_idx = int(np.ceil(s[min_idx - 1: min_idx + 1].sum() * 0.5))
        right_idx = int(np.floor(s[max_idx + 1: max_idx + 3].sum() * 0.5))
        yield left_idx, right_idx


def find_first_valid_index(st_lat, st_lng, ev_lat, ev_lng,
        ev_depth_in_km, delta):
    """
    Helper function to determine the first valid index.

    It will be determined by calculating the first possible theoretical
    arrival time.

    :param st_lat: The station latitude.
    :param st_lng: The station longitude.
    :param ev_lat: The event latitude.
    :param ev_lng: The event longitude.
    :param ev_depth_in_km: The event depth in km.
    :param delta: The sample spacing of the data to convert the time to an
        index.
    """
    dist_in_deg = geodetics.locations2degrees(st_lat, st_lng, ev_lat, ev_lng)
    tts = getTravelTimes(dist_in_deg, ev_depth_in_km, model="ak135")
    first_tt_arrival = min([_i["time"] for _i in tts])
    return first_tt_arrival / delta


def select_windows_2(data_trace, synthetic_trace, ev_lat, ev_lng,
        ev_depth_in_km, st_lat, st_lng, dominant_period):
    """
    :param data_trace:
    :param synthetic_trace:
    :param ev_lat:
    :param ev_lng:
    :param ev_depth_in_km:
    :param st_lat:
    :param st_lng:
    :param dominant_period:
    """
    dt = synthetic_trace.stats.delta
    npts = synthetic_trace.stats.npts
    dist_in_deg = geodetics.locations2degrees(st_lat, st_lng, ev_lat, ev_lng)
    dist_in_km = geodetics.calcVincentyInverse(st_lat, st_lng, ev_lat,
        ev_lng)[0] / 1000.0
    tts = getTravelTimes(dist_in_deg, ev_depth_in_km, model="ak135")
    first_tt_arrival = min([_i["time"] for _i in tts])

    # The window length. Currently set to one dominant period of the
    # synthetics. Make sure it is an uneven number; just to have an easy
    # midpoint definition.
    window_length = int(round(float(dominant_period) / dt))

    if not window_length % 2:
        window_length += 1

    # Naive sliding window approach. Can be replaced by more efficient
    # variants if necessary.
    def window_generator(data_length, window_width):
        """

        :param data_length:
        :param window_width:
        """
        window_start = 0
        while True:
            window_end = window_start + window_width
            if window_end > data_length:
                break
            yield (window_start, window_end, window_start + window_width // 2)
            window_start += 1

    # Allocate arrays to collect the time dependent values.
    sliding_time_shift = np.ma.masked_all(npts, dtype="float32")
    max_cc_coeff = np.ma.masked_all(npts, dtype="float32")

    taper = np.hanning(window_length)

    for start_idx, end_idx, midpoint_idx in window_generator(npts,
            window_length):
        # Slice windows. Create a copy to be able to taper without affecting
        #  the original time series.
        data_window = data_trace.data[start_idx: end_idx].copy() * taper
        synthetic_window = synthetic_trace.data[start_idx: end_idx].copy() * \
            taper

        # Skip windows that have essentially no energy to avoid instabilities.
        if synthetic_window.ptp() < synthetic_trace.data.ptp() * 0.001:
            continue

        # Calculate the time shift. Here this is defined as the shift of the
        # synthetics relative to the data. So a value of 2 means that the
        # synthetics are 2 timesteps later then the data.
        cc = np.correlate(data_window, synthetic_window, mode="full")

        time_shift = cc.argmax() - window_length + 1
        # Express the time shift in fraction of dominant period.
        sliding_time_shift[midpoint_idx] = (time_shift * dt) / \
            dominant_period

        # Normalized cross correlation.
        max_cc_value = cc.max() / np.sqrt((synthetic_window ** 2).sum() *
            (data_window ** 2).sum())
        max_cc_coeff[midpoint_idx] = max_cc_value

    threshold_travel_time = 2.0

    # Step 1
    time_windows = np.ma.ones(npts)
    time_windows.mask = np.zeros(npts)

    # Step 2: Mark everything more then half a dominant period before the
    # first theoretical arrival as positive.
    time_windows.mask[:int(np.ceil((first_tt_arrival - dominant_period * 0.5)
        / dt))] = True

    # Step 3: Mark everything more then half a dominant period after the
    # chosen threshold surface wave velocity time as negative
    time_windows.mask[int(np.floor(dist_in_km /
        threshold_travel_time / dt)):] = True

    # Step 4: Mark everything with an absolute travel time shift of more then
    # 0.2 time the dominant period as negative
    time_windows.mask[np.abs(sliding_time_shift) > 0.2] = True

    # Step 5: Mark the area around every "travel time shift jump" (based on
    # the traveltime time difference) negative. The width of the area is
    # currently chosen to be a tenth of a dominant period to each side.
    sample_buffer = int(np.ceil(dominant_period / dt * 0.1))
    indices = np.ma.where(np.abs(np.diff(sliding_time_shift)) > 0.1)[0]
    for index in indices:
        time_windows.mask[index - sample_buffer: index + sample_buffer] = \
            True

    # Step 6: Mark all areas where the normalized cross correlation coefficient
    # is under 0.7 as negative
    time_windows.mask[max_cc_coeff < 0.7] = True

    # Step 7: Throw away all windows with a length of less then 0.5 the
    # dominant period.
    min_length = dominant_period / dt * 0.5
    final_windows = []
    for i in np.ma.flatnotmasked_contiguous(time_windows):
        if (i.stop - i.start) < min_length:
            continue
        # Now compare the energy in the data window in the synthetic window.
        # If they differ by more then one order of magnitude, discard them.
        data_energy = (data_trace.data[i.start: i.stop] ** 2).sum()
        synth_energy = (synthetic_trace.data[i.start: i.stop] ** 2).sum()
        energies = sorted([data_energy, synth_energy])
        if energies[1] > 10.0 * energies[0]:
            continue
        final_windows.append((i.start, i.stop))

    return final_windows


def select_windows(data_trace, synthetic_trace, ev_lat, ev_lng,
        ev_depth_in_km, st_lat, st_lng, dominant_period):
    """
    Window selection function.

    It takes two traces, a data trace and a synthetic trace. Both trace are
    assumed to already be processed. At the very least they have to have the
    same units and be defined at exactly the same time intervals. It follows
    that both have to have the same length and same sampling rate.

    Furthermore it is assumed that the first sample of both traces
    corresponds to the origin time of the event.

    The event and station parameters are needed to be able to calculate
    theoretical traveltimes.

    :param data_trace: The data trace.
    :type data_trace: obspy.core.trace.Trace
    :param synthetic_trace: The synthetic trace.
    :type synthetic_trace: obspy.core.trace.Trace
    :param ev_lat: The latitude of the seismic event.
    :type ev_lat: float
    :param ev_lng: The longitude of the seismic event.
    :type ev_lng: float
    :param ev_depth_in_km: The depth of the event in km.
    :type ev_depth_in_km: float
    :param st_lat: The latitude of the recording station.
    :type st_lat: float
    :param st_lng: The longitude of the recording station.
    :type st_lng: float
    :param dominant_period: The dominant period of the data. Used for some
        selection criteria.
    :type dominant_period: float
    """
    min_window_length = int(round(dominant_period /
        synthetic_trace.stats.delta))
    npts = synthetic_trace.stats.npts
    # Only data after the first possible theoretical arrival will be
    # considered.
    first_valid_index = find_first_valid_index(st_lat, st_lng, ev_lat,
        ev_lng, ev_depth_in_km, synthetic_trace.stats.delta)

    noise_level = np.abs(data_trace.data[:first_valid_index]).max()
    data_trace.stats.first_valid_index = first_valid_index
    data_trace.stats.noise_level = noise_level

    # Get the local extreme value of the data as well as the synthetics.
    data_p, data_t, data_extrema = find_local_extrema(data_trace.data,
        first_valid_index)
    synth_p, synth_t, synth_extrema = find_local_extrema(synthetic_trace.data,
        first_valid_index)

    # The actual window selection is handled via a simple boolean array.
    # True values are considered valid data points.
    window_mask = np.ones(len(data_trace.data), dtype="bool")
    window_mask[:first_valid_index] = False

    # Create the index distance curves for all metrics.
    peak_distance_data = complete_index_distance(data_p, npts)
    peak_distance_synth = complete_index_distance(synth_p, npts)
    trough_distance_data = complete_index_distance(data_t, npts)
    trough_distance_synth = complete_index_distance(synth_t, npts)
    extrema_distance_data = complete_index_distance(data_extrema, npts)
    extrema_distance_synth = complete_index_distance(synth_extrema, npts)

    # Calculate relative deviations between data and synthetics for all the
    # metrics.
    extrema_rel_diff = np.abs(extrema_distance_data - extrema_distance_synth) \
        / extrema_distance_synth
    peak_rel_diff = np.abs(peak_distance_data - peak_distance_synth) / \
        peak_distance_synth
    trough_rel_diff = np.abs(trough_distance_data - trough_distance_synth) / \
        trough_distance_synth

    # The finally used metric is the maximum of all the previously defined
    # metrics. This should ensure that the "wigglyness" between data and
    # synthetics is fairly similar.
    rel_diff_complete = np.maximum(np.maximum(extrema_rel_diff,
        peak_rel_diff), trough_rel_diff)

    # Apply it to the mask. The relative difference of 1.0 results in a
    # pretty large possible difference but still within one wavelength.
    # window_mask[rel_diff_complete > 1.0] = False

    # Now apply the skip detection for peaks and troughs and add it to the
    # same window mask. Only parts still set to True after everything will
    # be deemed appropriate.
    inverse_mask = np.zeros(npts, dtype="bool")
    for window in skip_finder(data_p, synth_p):
        inverse_mask[window[0]: window[1]] = True
    window_mask &= inverse_mask
    inverse_mask[:] = False
    for window in skip_finder(data_t, synth_t):
        inverse_mask[window[0]: window[1]] = True
    window_mask &= inverse_mask

    window_mask = np.ma.masked_array(window_mask, mask=np.invert(window_mask))

    # Now assemble the windows and apply some more selection algorithms.
    final_windows = []
    for i in np.ma.flatnotmasked_contiguous(window_mask):
        # Use the middle index to get the current peak-to-peak and
        # trough-to-trough distance for the synthetics. Choose the maximum
        # of both the be the minimum of the acceptable window length.
        window_length = i.stop - i.start
        if window_length < min_window_length:
            continue

        # Make sure the window is at least 10 times above the noise level
        # for data and synthetics.
        if np.abs(data_trace.data[i.start: i.stop]).max() \
                < (5 * noise_level) or \
                np.abs(synthetic_trace.data[i.start: i .stop]).max() \
                < (5 * noise_level):
            continue

        # Now compare the energy in the data window in the synthetic window.
        # If they differ by more then one order of magnitude, discard them.
        data_energy = (data_trace.data[i.start: i.stop] ** 2).sum()
        synth_energy = (synthetic_trace.data[i.start: i.stop] ** 2).sum()
        energies = sorted([data_energy, synth_energy])
        if energies[1] > 10.0 * energies[0]:
            continue
        # Potentially merge with the previous window if there is no
        # difference.
        if final_windows and (final_windows[-1][1] + 1) == i.start:
            final_windows[-1] = (final_windows[-1][0], i.stop)
        else:
            final_windows.append((i.start, i.stop))

    return final_windows


def plot_windows(data_trace, synthetic_trace, windows, dominant_period,
        filename=None, debug=False):
    """
    Helper function plotting the picked windows in some variants. Useful for
    debugging and checking what's actually going on.

    If using the debug option, please use the same data_trace and
    synthetic_trace as you used for the select_windows() function. They will
    be augmented with certain values used for the debugging plots.

    :param data_trace: The data trace.
    :type data_trace: obspy.core.trace.Trace
    :param synthetic_trace: The synthetic trace.
    :type synthetic_trace: obspy.core.trace.Trace
    :param windows: The windows, as returned by select_windows()
    :type windows: list
    :param dominant_period: The dominant period of the data. Used for the
        tapering.
    :type dominant_period: float
    :param filename: If given, a file will be written. Otherwise the plot
        will be shown.
    :type filename: basestring
    :param debug: Toggle plotting debugging information. Optional. Defaults
        to False.
    :type debug: bool
    """
    import matplotlib.pylab as plt
    from obspy.signal.invsim import cosTaper

    plt.figure(figsize=(16, 10))
    plt.subplots_adjust(hspace=0.3)

    npts = synthetic_trace.stats.npts

    # Plot the raw data.
    time_array = np.linspace(0, (npts - 1) * synthetic_trace.stats.delta, npts)
    plt.subplot(411)
    plt.plot(time_array, data_trace.data, color="black", label="data")
    plt.plot(time_array, synthetic_trace.data, color="red",
        label="synthetics")
    plt.xlim(0, time_array[-1])
    plt.title("Raw data")

    # Plot the chosen windows.
    bottom = np.ones(npts) * -10.0
    top = np.ones(npts) * 10.0
    for left_idx, right_idx in windows:
        top[left_idx: right_idx + 1] = -10.0
    plt.subplot(412)
    plt.plot(time_array, data_trace.data, color="black", label="data")
    plt.plot(time_array, synthetic_trace.data, color="red",
             label="synthetics")
    ymin, ymax = plt.ylim()
    plt.fill_between(time_array, bottom, top, color="red", alpha="0.5")
    plt.xlim(0, time_array[-1])
    plt.ylim(ymin, ymax)
    plt.title("Chosen windows")

    # Plot the tapered data.
    final_data = np.zeros(npts)
    final_data_scaled = np.zeros(npts)
    synth_data = np.zeros(npts)
    synth_data_scaled = np.zeros(npts)

    for left_idx, right_idx in windows:
        right_idx += 1
        length = right_idx - left_idx

        # Setup the taper.
        p = (dominant_period / synthetic_trace.stats.delta / length) / 2.0
        if p >= 0.5:
            p = 0.49
        elif p < 0.1:
            p = 0.1
        taper = cosTaper(length, p=p)

        data_window = taper * data_trace.data[left_idx: right_idx].copy()
        synth_window = taper * synthetic_trace.data[left_idx: right_idx].copy()

        data_window_scaled = data_window / data_window.ptp() * 2.0
        synth_window_scaled = synth_window / synth_window.ptp() * 2.0

        final_data[left_idx: right_idx] = data_window
        synth_data[left_idx: right_idx] = synth_window
        final_data_scaled[left_idx: right_idx] = data_window_scaled
        synth_data_scaled[left_idx: right_idx] = synth_window_scaled

    plt.subplot(413)
    plt.plot(time_array, final_data, color="black")
    plt.plot(time_array, synth_data, color="red")
    plt.xlim(0, time_array[-1])
    plt.title("Tapered windows")

    plt.subplot(414)
    plt.plot(time_array, final_data_scaled, color="black")
    plt.plot(time_array, synth_data_scaled, color="red")
    plt.xlim(0, time_array[-1])
    plt.title("Tapered windows, scaled to same amplitude")

    if debug:
        first_valid_index = data_trace.stats.first_valid_index * \
            synthetic_trace.stats.delta
        noise_level = data_trace.stats.noise_level

        data_p, data_t, data_e = find_local_extrema(data_trace.data,
            start_index=first_valid_index)
        synth_p, synth_t, synth_e = find_local_extrema(synthetic_trace.data,
            start_index=first_valid_index)

        for _i in xrange(1, 3):
            plt.subplot(4, 1, _i)
            ymin, ymax = plt.ylim()
            xmin, xmax = plt.xlim()
            plt.vlines(first_valid_index, ymin, ymax, color="green",
                label="Theoretical First Arrival")
            plt.hlines(noise_level, xmin, xmax, color="0.5",
                       label="Noise Level", linestyles="--")
            plt.hlines(-noise_level, xmin, xmax, color="0.5", linestyles="--")

            plt.hlines(noise_level * 5, xmin, xmax, color="0.8",
                       label="Minimal acceptable amplitude", linestyles="--")
            plt.hlines(-noise_level * 5, xmin, xmax, color="0.8",
                       linestyles="--")
            if _i == 2:
                plt.scatter(time_array[data_e], data_trace.data[data_e],
                            color="black", s=10)
                plt.scatter(time_array[synth_e], synthetic_trace.data[synth_e],
                            color="red", s=10)
            plt.ylim(ymin, ymax)
            plt.xlim(xmin, xmax)

        plt.subplot(411)
        plt.legend(prop={"size": "small"})

    plt.suptitle(data_trace.id)

    if filename:
        plt.savefig(filename)
    else:
        plt.show()


if __name__ == '__main__':
    import doctest
    doctest.testmod()